"""Daily-digest fan-out load check: N users due at the same minute.

Seeds N demo users (default 300) with a due DailyBriefPreference, triggers
``puregamma.dispatch_due_daily_briefs`` (celery ``send_task`` or direct
in-process function), measures completion, then runs duplicate checks on
Report / NotificationDelivery rows. Exits non-zero on duplicates or timeout.

REQUIREMENTS:
* ``--via celery`` needs a reachable broker+result backend (redis) AND at
  least one running worker (``celery -A packages.workers.celery_app worker``).
* DB verification needs the app's database: run on the server with the app
  environment, or pass --database-url / PG_LOAD_DATABASE_URL.
* The production orchestrator caps one run at 100 due preferences, so the
  trigger loops until a run reports ``due == 0`` (expected: ceil(N/100) waves).

Usage (on the server / against staging):

    python tests/load/digest_fanout.py --users 300 --mode db --via celery
    python tests/load/digest_fanout.py --users 60  --mode db --via direct

    PG_LOAD_DATABASE_URL=postgresql+psycopg://... \
        python tests/load/digest_fanout.py --mode db --via celery

API seeding note: ``--mode api`` provisions users via the dev-only mock login
and the preference PUT endpoint; the API never schedules a preference in the
past, so those users only become due at their next local slot — use
``--mode db`` for the deterministic same-minute fan-out.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEFAULT_DATABASE_URL = os.environ.get("PG_LOAD_DATABASE_URL", "")
DEFAULT_BASE_URL = os.environ.get("PG_LOAD_BASE_URL", "http://localhost:8000")
USER_PREFIX = "digest-load-"


def _session(database_url: str):
    """Session bound to --database-url, or to the app's configured database."""
    if database_url:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(database_url, future=True)
        return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()
    from packages.database.session import SessionLocal

    return SessionLocal()


def seed_users_db(db, count: int) -> list[str]:
    """Bulk-insert demo users already due at this minute. Returns user ids."""
    from packages.database.models import DailyBriefPreference, User, UserPreference, utcnow

    due_at = utcnow() - timedelta(minutes=1)
    stamp = int(time.time())
    users = [
        User(
            email=f"{USER_PREFIX}{stamp}-{index}@puregamma.ai",
            name=f"{USER_PREFIX}{index}",
            role="user",
            plan="Pro",
            credit_balance=1_000,
        )
        for index in range(count)
    ]
    db.add_all(users)
    db.flush()
    user_ids = [user.id for user in users]
    db.add_all(
        UserPreference(
            user_id=user.id,
            email_recipient=user.email,
            telegram_chat_id="mock-telegram-chat",
            notification_channels=["email"],
        )
        for user in users
    )
    db.add_all(
        DailyBriefPreference(
            user_id=user.id,
            enabled=True,
            timezone="UTC",
            local_time="08:30",
            channel="email",
            channels=["email"],
            report_types=None,
            locale="en",
            next_delivery_at=due_at,
            recipient=user.email,
        )
        for user in users
    )
    db.commit()
    return user_ids


def seed_users_api(base_url: str, count: int) -> None:
    """Provision users through the dev-only API (see module docstring note)."""
    import httpx

    stamp = int(time.time())
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=30.0) as client:
        for index in range(count):
            email = f"{USER_PREFIX}{stamp}-{index}@puregamma.ai"
            login = client.post("/auth/mock-login", json={"email": email, "name": f"{USER_PREFIX}{index}"})
            login.raise_for_status()
            preference = client.put(
                "/notifications/preferences/daily-brief",
                json={"enabled": True, "channels": ["email"], "timezone": "UTC", "local_time": "08:30"},
                cookies=login.cookies,
            )
            preference.raise_for_status()


def trigger_direct() -> dict:
    """Run the orchestrator in-process until the due set drains."""
    from packages.workers import tasks

    waves = 0
    totals = {"due": 0, "sent": 0, "skipped": 0, "failed": 0}
    while True:
        result = tasks.dispatch_due_daily_briefs()
        waves += 1
        for key in totals:
            totals[key] += int(result.get(key, 0))
        if result.get("due", 0) == 0:
            break
        if waves >= 20:
            raise RuntimeError(f"orchestrator did not drain within 20 waves: {result}")
    totals["waves"] = waves
    return totals


def trigger_celery(timeout_s: float) -> dict:
    """Send the celery task wave by wave until a wave reports due == 0."""
    from packages.workers.celery_app import celery_app

    deadline = time.monotonic() + timeout_s
    waves = 0
    totals = {"due": 0, "sent": 0, "skipped": 0, "failed": 0}
    while True:
        async_result = celery_app.send_task("puregamma.dispatch_due_daily_briefs")
        while not async_result.ready():
            if time.monotonic() > deadline:
                raise TimeoutError("celery wave did not finish before --timeout")
            time.sleep(2)
        result = async_result.result or {}
        waves += 1
        for key in totals:
            totals[key] += int(result.get(key, 0))
        if result.get("due", 0) == 0:
            break
        if waves >= 20:
            raise RuntimeError(f"orchestrator did not drain within 20 waves: {result}")
    totals["waves"] = waves
    return totals


def duplicate_checks(db, user_ids: list[str]) -> dict:
    from sqlalchemy import func

    from packages.database.models import DailyBriefPreference, NotificationDelivery, Report

    duplicate_reports = (
        db.query(Report.user_id, Report.report_type, Report.report_date, func.count())
        .filter(Report.user_id.in_(user_ids))
        .group_by(Report.user_id, Report.report_type, Report.report_date)
        .having(func.count() > 1)
        .count()
    )
    duplicate_deliveries = (
        db.query(NotificationDelivery.idempotency_key, func.count())
        .filter(NotificationDelivery.user_id.in_(user_ids))
        .group_by(NotificationDelivery.idempotency_key)
        .having(func.count() > 1)
        .count()
    )
    reports = db.query(Report).filter(Report.user_id.in_(user_ids)).count()
    deliveries = db.query(NotificationDelivery).filter(NotificationDelivery.user_id.in_(user_ids)).count()
    max_failures = (
        db.query(func.max(DailyBriefPreference.failure_count))
        .filter(DailyBriefPreference.user_id.in_(user_ids))
        .scalar()
    )
    return {
        "reports": reports,
        "deliveries": deliveries,
        "duplicate_reports": duplicate_reports,
        "duplicate_deliveries": duplicate_deliveries,
        "max_failure_count": max_failures or 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--users", type=int, default=300, help="demo users to seed (default 300)")
    parser.add_argument("--mode", choices=["db", "api"], default="db", help="seed via DB bulk insert or dev API")
    parser.add_argument("--via", choices=["celery", "direct"], default="celery", help="trigger path")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL for --mode api (env PG_LOAD_BASE_URL)")
    parser.add_argument("--database-url", default=DEFAULT_DATABASE_URL, help="DB URL for verification (env PG_LOAD_DATABASE_URL); defaults to the app settings")
    parser.add_argument("--timeout", type=float, default=900, help="completion timeout seconds (default 900)")
    args = parser.parse_args()

    db = _session(args.database_url)
    try:
        started = time.perf_counter()
        if args.mode == "db":
            user_ids = seed_users_db(db, args.users)
            print(f"seeded {len(user_ids)} users due at the same minute (mode=db)")
        else:
            seed_users_api(args.base_url, args.users)
            print(f"provisioned {args.users} users via API (due at their next local slot)")
            user_ids = None

        if args.via == "celery":
            totals = trigger_celery(args.timeout)
        else:
            totals = trigger_direct()
        elapsed = time.perf_counter() - started
        print(f"trigger complete: waves={totals['waves']} due={totals['due']} sent={totals['sent']} "
              f"skipped={totals['skipped']} failed={totals['failed']} wall_seconds={elapsed:.2f}")

        if user_ids is None:
            print("duplicate checks require --mode db (API seeding does not expose user ids)")
            return 0
        checks = duplicate_checks(db, user_ids)
        print("-" * 64)
        print(f"reports={checks['reports']} deliveries={checks['deliveries']}")
        print(f"duplicate_reports={checks['duplicate_reports']} duplicate_deliveries={checks['duplicate_deliveries']}")
        print(f"max_failure_count={checks['max_failure_count']}")
        ok = (
            checks["duplicate_reports"] == 0
            and checks["duplicate_deliveries"] == 0
            and checks["max_failure_count"] <= 1
            and totals["failed"] == 0
        )
        print("RESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
