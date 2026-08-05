"""Concurrent SSE stream load check for the agent fast path.

Opens N concurrent SSE streams against
``POST /api/agent/conversations/{conversation_id}/messages`` (the documented
SSE endpoint; one fresh conversation per stream), measures per-stream
time-to-first-event (TTFE), and prints p50/p95/max with PASS/FAIL vs the 2s
acceptance threshold. Exits non-zero on regression.

Usage (live server — never run against production from a dev box without
explicit approval):

    python tests/load/sse_concurrency.py \
        --base-url http://localhost:8000 --token <jwt> --streams 50

Defaults may come from the environment:

    PG_LOAD_BASE_URL=http://localhost:8000 PG_LOAD_TOKEN=<jwt> \
        python tests/load/sse_concurrency.py --streams 50

Offline validation (no server, in-memory app over ASGI transport):

    python tests/load/sse_concurrency.py --self-test --streams 3
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

import httpx

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEFAULT_BASE_URL = os.environ.get("PG_LOAD_BASE_URL", "http://localhost:8000")
DEFAULT_TOKEN = os.environ.get("PG_LOAD_TOKEN", "")
SSE_PATH = "/api/agent/conversations/{conversation_id}/messages"
CONVERSATIONS_PATH = "/api/agent/conversations"
PROMPT = "隔夜有什么重要的事？"  # overnight fast-path intent
TIMEOUT_S = 30.0


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1))))
    return ordered[rank]


async def _create_conversation(client: httpx.AsyncClient, token: str, index: int) -> str:
    response = await client.post(
        CONVERSATIONS_PATH,
        json={"title": f"sse-load-{index}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    return response.json()["conversation"]["id"]


async def _open_stream(client: httpx.AsyncClient, conversation_id: str, token: str) -> dict:
    started = time.perf_counter()
    ttfe = None
    status = None
    error = None
    try:
        async with client.stream(
            "POST",
            SSE_PATH.format(conversation_id=conversation_id),
            json={"content": PROMPT, "locale": "zh"},
            headers={"Authorization": f"Bearer {token}"},
        ) as response:
            status = response.status_code
            if status != 200:
                await response.aread()
                error = f"http_{status}"
            else:
                async for chunk in response.aiter_bytes():
                    if chunk:
                        ttfe = time.perf_counter() - started
                        break
    except Exception as exc:  # noqa: BLE001 - load tool: record, don't crash
        error = f"{type(exc).__name__}: {exc}"
    if ttfe is None:
        ttfe = time.perf_counter() - started
    return {"ttfe": ttfe, "status": status, "error": error}


async def run_load(client: httpx.AsyncClient, token: str, streams: int, threshold_s: float) -> int:
    print(f"creating {streams} conversations ...")
    conversation_ids = await asyncio.gather(
        *[_create_conversation(client, token, index) for index in range(streams)]
    )
    print(f"opening {streams} concurrent SSE streams ...")
    results = await asyncio.gather(
        *[_open_stream(client, conversation_id, token) for conversation_id in conversation_ids]
    )

    times = [row["ttfe"] for row in results]
    errors = [row for row in results if row["error"] or row["ttfe"] is None]
    p50 = _percentile(times, 50)
    p95 = _percentile(times, 95)
    worst = max(times)
    ok = not errors and p95 <= threshold_s
    print("-" * 64)
    print(f"streams={len(results)} errors={len(errors)} threshold_s={threshold_s}")
    print(f"ttfe_p50={p50 * 1000:.0f}ms ttfe_p95={p95 * 1000:.0f}ms ttfe_max={worst * 1000:.0f}ms")
    for row in errors[:10]:
        print(f"  error: status={row['status']} {row['error']}")
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


class _EchoProvider:
    """Offline provider for --self-test; echoes instantly."""

    provider_name = "mock"
    model = "echo-model"
    configured = True
    last_error = None

    def stream_chat(self, messages, **kwargs):
        from packages.agents.llm.schemas import LLMStreamChunk

        payload = "\n".join(message.content for message in messages)
        yield LLMStreamChunk(delta=payload[:8000], provider="mock", model="echo-model")
        yield LLMStreamChunk(done=True, provider="mock", model="echo-model", prompt_tokens=64, completion_tokens=256)


async def _self_test(streams: int, threshold_s: float) -> int:
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
    from apps.api.config import Settings
    from apps.api.dependencies import create_access_token, get_db
    from apps.api.main import app
    from apps.api.services import agent_answer_service, agent_service
    from packages.database.models import Base, User, UserPreference
    from packages.database.seed import seed_all

    db_path = os.path.join(tempfile.mkdtemp(prefix="pg-sse-selftest-"), "selftest.db")
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
    user = User(
        email="sse-load-selftest@puregamma.ai",
        name="sse-load-selftest",
        role="user",
        plan="Pro",
        credit_balance=1_000_000,
    )
    db.add(user)
    db.flush()
    db.add(UserPreference(user_id=user.id, email_recipient=user.email))
    db.commit()
    token = create_access_token(user)
    db.close()

    echo_settings = Settings(enable_mock_agent=True, llm_provider="mock", agent_model="echo-model")
    agent_service.get_settings = lambda: echo_settings  # noqa: E731
    agent_service.get_agent_llm_provider = lambda selected_model=None: _EchoProvider()  # noqa: E731
    agent_answer_service.get_settings = lambda: echo_settings  # noqa: E731

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://selftest.local", timeout=TIMEOUT_S
        ) as client:
            return await run_load(client, token, streams, threshold_s)
    finally:
        app.dependency_overrides.clear()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL (env PG_LOAD_BASE_URL)")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="Bearer JWT (env PG_LOAD_TOKEN)")
    parser.add_argument("--streams", type=int, default=50, help="concurrent SSE streams (default 50)")
    parser.add_argument("--threshold", type=float, default=2.0, help="TTFE p95 threshold in seconds (default 2.0)")
    parser.add_argument("--self-test", action="store_true", help="offline in-process dry run (no server needed)")
    args = parser.parse_args()

    if args.self_test:
        return asyncio.run(_self_test(args.streams, args.threshold))
    if not args.token:
        print("error: --token (or PG_LOAD_TOKEN) is required against a live server", file=sys.stderr)
        return 2

    async def _run() -> int:
        async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=TIMEOUT_S) as client:
            return await run_load(client, args.token, args.streams, args.threshold)

    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
