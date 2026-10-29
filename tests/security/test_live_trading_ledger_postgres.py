"""Ledger writes against a real Postgres.

SQLite silently accepts ``SELECT sum(...) FOR UPDATE``; Postgres rejects it
("FOR UPDATE is not allowed with aggregate functions"), which made every
``post_entry`` fail in production. These tests only run when
``PUREGAMMA_TEST_POSTGRES_DSN`` points at a disposable Postgres database
(e.g. ``postgresql+psycopg://postgres:postgres@localhost:5432/postgres``).
All objects are created in a throwaway schema that is dropped afterwards.
"""

from __future__ import annotations

import os
import threading
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from packages.database.models import Base, LedgerEntry, TradingAccount, User
from packages.live_trading import ledger

DSN = os.environ.get("PUREGAMMA_TEST_POSTGRES_DSN", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN, reason="PUREGAMMA_TEST_POSTGRES_DSN not set; Postgres ledger tests skipped"
)


@pytest.fixture()
def pg_sessionmaker():
    schema = f"ledger_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(DSN, future=True)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        DSN,
        future=True,
        connect_args={"options": f"-csearch_path={schema}"},
        pool_size=10,
    )
    try:
        Base.metadata.create_all(engine)
        yield sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _seed_account(Session) -> tuple[str, str]:
    with Session() as session:
        user = User(email=f"{uuid.uuid4().hex}@pg.test", name="pg", role="user", plan="Free")
        session.add(user)
        session.flush()
        account = TradingAccount(
            user_id=user.id,
            name="pg-live",
            venue="MOCK",
            account_type="LIVE",
            base_currency="USD",
            status="ACTIVE",
        )
        session.add(account)
        session.commit()
        return user.id, account.id


def test_post_entry_works_on_postgres(pg_sessionmaker):
    user_id, account_id = _seed_account(pg_sessionmaker)
    with pg_sessionmaker() as session:
        deposit = ledger.post_entry(
            session,
            user_id=user_id,
            account_id=account_id,
            entry_type="cash_deposit",
            amount="1000",
            idempotency_key="pg:deposit",
            trace_id="pg",
        )
        buy = ledger.post_entry(
            session,
            user_id=user_id,
            account_id=account_id,
            entry_type="trade_buy",
            amount="-250",
            symbol="BTCUSDT",
            quantity="2.5",
            price="100",
            idempotency_key="pg:buy",
            trace_id="pg",
        )
        session.commit()
        assert deposit.balance_after == Decimal("1000")
        assert buy.balance_after == Decimal("750")
        assert ledger.cash_balance(session, account_id, for_update=True) == Decimal("750")
        # Replays are idempotent.
        again = ledger.post_entry(
            session,
            user_id=user_id,
            account_id=account_id,
            entry_type="cash_deposit",
            amount="1000",
            idempotency_key="pg:deposit",
            trace_id="pg",
        )
        assert again.id == deposit.id


def test_concurrent_post_entry_serializes_balance_after(pg_sessionmaker):
    user_id, account_id = _seed_account(pg_sessionmaker)
    writers = 8
    barrier = threading.Barrier(writers)
    errors: list[BaseException] = []

    def write(index: int) -> None:
        try:
            with pg_sessionmaker() as session:
                barrier.wait(timeout=10)
                ledger.post_entry(
                    session,
                    user_id=user_id,
                    account_id=account_id,
                    entry_type="cash_deposit",
                    amount="1",
                    idempotency_key=f"pg:concurrent:{index}",
                    trace_id="pg",
                )
                session.commit()
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(i,)) for i in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not errors, errors

    with pg_sessionmaker() as session:
        balances = sorted(
            row.balance_after
            for row in session.query(LedgerEntry).filter_by(account_id=account_id).all()
        )
    # Without per-account serialization concurrent writers read the same
    # running sum and record duplicate balance_after values.
    assert balances == [Decimal(i) for i in range(1, writers + 1)]


def test_keyset_pages_with_identical_timestamps_neither_repeat_nor_skip(pg_sessionmaker):
    """Postgres stores microseconds and compares tuples natively; rows that
    share one created_at must still split across pages by id, exactly once."""
    from datetime import datetime, timezone

    from packages.live_trading import ledger_view

    user_id, account_id = _seed_account(pg_sessionmaker)
    same = datetime(2026, 10, 29, 12, 0, 0, 123456, tzinfo=timezone.utc)
    with pg_sessionmaker() as session:
        for index in range(23):
            at = same if index < 17 else same.replace(second=index)
            session.add(
                LedgerEntry(
                    user_id=user_id, account_id=account_id, entry_type="cash_deposit",
                    amount=Decimal("1"), currency="USD", idempotency_key=f"pg:tie:{index}",
                    trace_id="pg", created_at=at,
                )
            )
        session.commit()

    for page_size in (1, 4, 5, 17, 22):
        seen: list[str] = []
        cursor = None
        with pg_sessionmaker() as session:
            for _ in range(50):
                page = ledger_view.ledger_page(session, user_id, account_id=account_id, cursor=cursor, limit=page_size)
                assert len(page["entries"]) <= page_size
                seen.extend(row["id"] for row in page["entries"])
                cursor = page["next_cursor"]
                if not cursor:
                    break
        assert len(seen) == len(set(seen)) == 23, page_size

    with pg_sessionmaker() as session:
        # The service clamps whatever it is given (HTTP rejects these with 422).
        assert ledger_view.ledger_page(session, user_id, account_id=account_id, limit=10**9)["limit"] == ledger_view.MAX_PAGE_SIZE
        assert ledger_view.ledger_page(session, user_id, account_id=account_id, limit=0)["limit"] == 1
