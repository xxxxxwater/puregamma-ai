"""API latency sampler for the non-LLM read endpoints.

Samples /health, /ready (unauthenticated) and /api/research/today,
/portfolio, /reports (Bearer auth), N requests total (default 200) with
bounded concurrency (default 20), and reports p50/p95/max per endpoint
against the 500ms non-LLM p95 target. Exits non-zero on regression or 5xx.

Usage (live server):

    python tests/load/api_latency.py \
        --base-url http://localhost:8000 --token <jwt> --requests 200 --concurrency 20

Defaults may come from the environment:

    PG_LOAD_BASE_URL=http://localhost:8000 PG_LOAD_TOKEN=<jwt> \
        python tests/load/api_latency.py

Offline validation (no server, in-memory app over ASGI transport):

    python tests/load/api_latency.py --self-test --requests 40 --concurrency 8
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from collections import defaultdict

import httpx

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEFAULT_BASE_URL = os.environ.get("PG_LOAD_BASE_URL", "http://localhost:8000")
DEFAULT_TOKEN = os.environ.get("PG_LOAD_TOKEN", "")
PUBLIC_ENDPOINTS = ("/health", "/ready")
AUTH_ENDPOINTS = ("/api/research/today", "/portfolio", "/reports")
TIMEOUT_S = 15.0


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1))))
    return ordered[rank]


async def _sample(client: httpx.AsyncClient, path: str, token: str | None, results: dict, semaphore: asyncio.Semaphore):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with semaphore:
        started = time.perf_counter()
        status = None
        error = None
        try:
            response = await client.get(path, headers=headers)
            status = response.status_code
        except Exception as exc:  # noqa: BLE001 - load tool: record, don't crash
            error = f"{type(exc).__name__}: {exc}"
        elapsed = time.perf_counter() - started
    results[path].append({"latency": elapsed, "status": status, "error": error})


async def run_load(client: httpx.AsyncClient, token: str | None, requests: int, concurrency: int, threshold_s: float) -> int:
    endpoints = list(PUBLIC_ENDPOINTS) + list(AUTH_ENDPOINTS)
    results: dict[str, list[dict]] = defaultdict(list)
    semaphore = asyncio.Semaphore(concurrency)
    await asyncio.gather(
        *[
            _sample(client, endpoints[index % len(endpoints)], token, results, semaphore)
            for index in range(requests)
        ]
    )

    print("-" * 72)
    print(f"requests={requests} concurrency={concurrency} threshold_s={threshold_s}")
    ok = True
    for path in endpoints:
        rows = results[path]
        latencies = [row["latency"] for row in rows]
        errors = [row for row in rows if row["error"] or (row["status"] or 500) >= 500]
        auth_failures = [row for row in rows if row["status"] in {401, 403}]
        p50 = _percentile(latencies, 50)
        p95 = _percentile(latencies, 95)
        worst = max(latencies)
        endpoint_ok = not errors and p95 <= threshold_s
        ok = ok and endpoint_ok and not auth_failures
        print(
            f"{path:26s} n={len(rows):3d} p50={p50 * 1000:6.0f}ms p95={p95 * 1000:6.0f}ms "
            f"max={worst * 1000:6.0f}ms 5xx={len(errors)} auth_fail={len(auth_failures)} "
            f"{'ok' if endpoint_ok else 'FAIL'}"
        )
        for row in errors[:5]:
            print(f"    error: status={row['status']} {row['error']}")
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


async def _self_test(requests: int, concurrency: int, threshold_s: float) -> int:
    """In-process dry run: temp-file WAL SQLite app over httpx ASGITransport.

    A file-backed engine with a real connection pool (not the in-memory
    StaticPool) is used so concurrent requests get per-request sessions on
    separate connections — much closer to production concurrency semantics.
    """
    import tempfile

    # Offline validation always runs a development app: force this BEFORE any
    # app import (the server .env is production and would fail validation).
    os.environ["APP_ENV"] = "development"
    os.environ["ENABLE_MOCK_MARKET_DATA"] = "true"

    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from apps.api.dependencies import create_access_token, get_db
    from apps.api.main import app
    from packages.database import session as session_module
    from packages.database.models import Base
    from packages.database.models import User as _User
    from packages.database.seed import seed_all

    db_path = os.path.join(tempfile.mkdtemp(prefix="pg-latency-selftest-"), "selftest.db")
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA busy_timeout=10000")

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = session_factory()
    seed_all(db)
    demo = db.query(_User).filter(_User.email == "demo@puregamma.ai").one()
    token = create_access_token(demo)
    db.close()

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    # /ready resolves SessionLocal per request; point it at the same engine.
    original_session_local = session_module.SessionLocal
    session_module.SessionLocal = session_factory
    # /ready pings redis per request; stub an always-up client so the offline
    # run doesn't pay redis-py's 1s connect timeout per call (an artifact of
    # the self-test environment, not of the app code path).
    from apps.api import redis_client as redis_client_module

    class _UpRedis:
        def ping(self):
            return True

    redis_client_module._client = _UpRedis()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://selftest.local", timeout=TIMEOUT_S
        ) as client:
            return await run_load(client, token, requests, concurrency, threshold_s)
    finally:
        session_module.SessionLocal = original_session_local
        app.dependency_overrides.clear()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL (env PG_LOAD_BASE_URL)")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="Bearer JWT (env PG_LOAD_TOKEN)")
    parser.add_argument("--requests", type=int, default=200, help="total requests (default 200)")
    parser.add_argument("--concurrency", type=int, default=20, help="max in-flight requests (default 20)")
    parser.add_argument("--threshold", type=float, default=0.5, help="p95 threshold in seconds (default 0.5)")
    parser.add_argument("--self-test", action="store_true", help="offline in-process dry run (no server needed)")
    args = parser.parse_args()

    if args.self_test:
        return asyncio.run(_self_test(args.requests, args.concurrency, args.threshold))
    if not args.token:
        print("error: --token (or PG_LOAD_TOKEN) is required against a live server", file=sys.stderr)
        return 2

    async def _run() -> int:
        async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=TIMEOUT_S) as client:
            return await run_load(client, args.token, args.requests, args.concurrency, args.threshold)

    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
