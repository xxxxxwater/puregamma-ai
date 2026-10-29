"""LIVE control-plane races against a real Postgres.

SQLite serializes every writer, so it cannot show what row locks do. These
run only with ``PUREGAMMA_TEST_POSTGRES_DSN`` (a disposable database; every
test uses a throwaway schema, see ``test_live_trading_ledger_postgres``).

- the same intent confirmed from many threads reaches the venue once and
  produces one order, and the losers never flip the intent to REJECTED;
- concurrent pause/resume leaves a consistent mandate and loses no audit row;
- a kill switch engaged while a cancel is in flight does not swallow the cancel;
- concurrent re-checks of one order query the venue once;
- concurrent final approvals of one proposal create one mandate.
"""

from __future__ import annotations

import dataclasses
import threading
import time
import uuid

import pytest

from apps.api.config import get_settings
from packages.database.models import (
    LiveOrder,
    LiveOrderIntent,
    TradingAuditLog,
    TradingKillSwitch,
    TradingMandate,
    TradingMandateProposal,
    User,
)
from packages.live_trading import control_plane, kill_switch, mandate_proposals, order_sync
from tests.security.test_live_trading_foundation import FakeGateway, _make_fill_order, _make_live_world
from tests.security.test_live_trading_ledger_postgres import DSN, pg_sessionmaker  # noqa: F401 - fixture

pytestmark = pytest.mark.skipif(
    not DSN, reason="PUREGAMMA_TEST_POSTGRES_DSN not set; Postgres concurrency tests skipped"
)


class CountingGateway(FakeGateway):
    """Thread-safe call counts; submit/cancel/query are slow enough to overlap."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.lock = threading.Lock()
        self.queries: list[str] = []
        self.cancels: list[str] = []

    def submit_order(self, payload):
        time.sleep(0.05)
        with self.lock:
            return super().submit_order(payload)

    def cancel_order(self, client_order_id, account_id, *, connection_id=None, symbol=None):
        time.sleep(0.05)
        with self.lock:
            self.cancels.append(client_order_id)
        return {"state": "canceled"}

    def query_order(self, client_order_id, account_id, *, connection_id=None, symbol=None):
        time.sleep(0.05)
        with self.lock:
            self.queries.append(client_order_id)
        return {"state": "unknown", "reason": "not visible yet"}


def _user(session, email: str | None = None, role: str = "user") -> User:
    user = User(email=email or f"{uuid.uuid4().hex}@pg.test", name="pg", role=role, plan="Max")
    session.add(user)
    session.commit()
    return user


def _run(workers: int, target) -> list[BaseException]:
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []

    def wrapped(index: int) -> None:
        try:
            barrier.wait(timeout=10)
            target(index)
        except BaseException as exc:  # surfaced to the test
            errors.append(exc)

    threads = [threading.Thread(target=wrapped, args=(i,)) for i in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads), "a worker hung (lock not released?)"
    return errors


def test_replaying_one_intent_concurrently_submits_once(pg_sessionmaker, monkeypatch):  # noqa: F811
    with pg_sessionmaker() as session:
        user = _user(session)
        world = _make_live_world(session, user, monkeypatch)
        gateway = CountingGateway()
        preview = control_plane.preview_order(
            session, user.id, mandate_id=world["mandate"].id, symbol="BTCUSDT", side="buy", quantity="0.5", gateway=gateway
        )
        intent_id, phrase, user_id = preview["intent"].id, preview["confirmation"], user.id

    results: list[str] = []

    def confirm(_: int) -> None:
        with pg_sessionmaker() as session:
            order = control_plane.confirm_order(
                session, user_id, order_intent_id=intent_id, confirmation=phrase, gateway=gateway
            )
            results.append(order.id)

    errors = _run(6, confirm)
    assert not errors, errors
    assert len(gateway.submitted) == 1
    assert len(set(results)) == 1 and len(results) == 6
    with pg_sessionmaker() as session:
        assert session.query(LiveOrder).filter_by(order_intent_id=intent_id).count() == 1
        assert session.get(LiveOrderIntent, intent_id).status == "APPROVED"

    # A later replay (e.g. the client retrying after a timeout) is the same order.
    with pg_sessionmaker() as session:
        again = control_plane.confirm_order(session, user_id, order_intent_id=intent_id, confirmation=phrase, gateway=gateway)
        assert again.id == results[0]
    assert len(gateway.submitted) == 1


def test_concurrent_pause_and_resume_stay_consistent_and_fully_audited(pg_sessionmaker, monkeypatch):  # noqa: F811
    with pg_sessionmaker() as session:
        user = _user(session)
        world = _make_live_world(session, user, monkeypatch)
        mandate_id, user_id = world["mandate"].id, user.id

    def flip(index: int) -> None:
        for round_ in range(4):
            with pg_sessionmaker() as session:
                if (index + round_) % 2 == 0:
                    control_plane.pause_mandate(session, user_id, mandate_id, reason=f"pause {index}/{round_}")
                else:
                    try:
                        control_plane.resume_mandate(session, user_id, mandate_id, confirmation=f"RESUME {mandate_id}")
                    except control_plane.ControlPlaneError:
                        pass

    errors = _run(6, flip)
    assert not errors, errors
    with pg_sessionmaker() as session:
        mandate = session.get(TradingMandate, mandate_id)
        events = [
            row.action
            for row in session.query(TradingAuditLog)
            .filter(TradingAuditLog.action.in_(["LIVE_MANDATE_PAUSE", "LIVE_MANDATE_RESUME"]))
            .order_by(TradingAuditLog.created_at.asc(), TradingAuditLog.id.asc())
            .all()
        ]
    assert events, "no transition was audited"
    # Calls are serialized by the mandate row lock and no-ops are not
    # audited, so every real transition must alternate PAUSE/RESUME starting
    # from the unpaused mandate. A lost audit row shows up as a repeat.
    expected = ["LIVE_MANDATE_PAUSE" if i % 2 == 0 else "LIVE_MANDATE_RESUME" for i in range(len(events))]
    assert events == expected
    assert mandate.paused == (events[-1] == "LIVE_MANDATE_PAUSE")
    if mandate.paused:
        assert mandate.pause_reason
    else:
        assert mandate.pause_reason is None and mandate.status == "active"


def test_a_kill_switch_engaged_mid_cancel_does_not_swallow_the_cancel(pg_sessionmaker, monkeypatch):  # noqa: F811
    with pg_sessionmaker() as session:
        user = _user(session)
        world = _make_live_world(session, user, monkeypatch)
        orders = [_make_fill_order(session, user, world, side=side, quantity="0.1") for side in ("buy", "sell")]
        targets = [(order.client_order_id, order.id) for order in orders]
        user_id = user.id
    gateway = CountingGateway()

    def act(index: int) -> None:
        with pg_sessionmaker() as session:
            if index == 0:
                kill_switch.engage(session, scope="global", reason="incident")
                kill_switch.engage(session, scope="user", scope_id=user_id, reason="incident")
                session.commit()
            else:
                client_order_id, _ = targets[index - 1]
                control_plane.cancel_order(session, user_id, client_order_id, gateway=gateway)

    errors = _run(3, act)
    assert not errors, errors
    with pg_sessionmaker() as session:
        for client_order_id, order_id in targets:
            assert session.get(LiveOrder, order_id).status == "canceled"
            assert session.query(TradingAuditLog).filter(
                TradingAuditLog.action == "LIVE_ORDER_CANCEL",
                TradingAuditLog.request_json.isnot(None),
                TradingAuditLog.result_json["order_id"].as_string() == order_id,
            ).count() == 1
        assert session.query(TradingKillSwitch).filter_by(state="active").count() == 2
    assert sorted(gateway.cancels) == sorted(cid for cid, _ in targets)


def test_concurrent_rechecks_query_the_venue_once(pg_sessionmaker, monkeypatch):  # noqa: F811
    settings = dataclasses.replace(get_settings(), live_order_recheck_enabled=True, live_order_recheck_min_interval_seconds=60)
    monkeypatch.setattr(order_sync, "get_settings", lambda: settings)
    with pg_sessionmaker() as session:
        user = _user(session)
        world = _make_live_world(session, user, monkeypatch)
        order = _make_fill_order(session, user, world, side="buy", quantity="0.1")
        order.status = "unknown"
        session.commit()
        order_id, user_id = order.id, user.id
    gateway = CountingGateway()
    outcomes: list[str] = []

    def recheck(_: int) -> None:
        with pg_sessionmaker() as session:
            try:
                order_sync.request_recheck(session, user_id, order_id, gateway=gateway)
                outcomes.append("ok")
            except order_sync.RecheckRateLimited:
                outcomes.append("limited")

    errors = _run(5, recheck)
    assert not errors, errors
    assert sorted(outcomes) == ["limited"] * 4 + ["ok"]
    assert len(gateway.queries) == 1 and gateway.submitted == []
    with pg_sessionmaker() as session:
        assert session.query(TradingAuditLog).filter_by(action=order_sync.RECHECK_ACTION).count() == 1
        assert session.query(LiveOrder).count() == 1


def test_concurrent_final_approvals_create_one_mandate(pg_sessionmaker, monkeypatch):  # noqa: F811
    settings = dataclasses.replace(get_settings(), live_mandate_proposals_enabled=True)
    monkeypatch.setattr(mandate_proposals, "get_settings", lambda: settings)
    with pg_sessionmaker() as session:
        owner = _user(session)
        world = _make_live_world(session, owner, monkeypatch)
        admins = [_user(session, role="admin") for _ in range(4)]
        proposal = mandate_proposals.propose(
            session, owner, user_id=owner.id, reason="pg race",
            terms={
                "account_id": world["account"].id, "strategy_release_id": world["release"].id,
                "broker_connection_id": world["connection"].id, "allowed_symbols": ["BTCUSDT"], "allowed_side": "long",
                "max_total_notional": "5000", "max_per_order_notional": "500", "max_position_notional": "2000",
                "max_daily_loss": "200", "max_leverage": "1", "max_trades_per_day": 5, "max_order_frequency_seconds": 30,
            },
        )
        mandate_proposals.approve(session, admins[0], proposal["id"], note="first")
        admin_ids, proposal_id = [admin.id for admin in admins[1:]], proposal["id"]
        mandates_before = session.query(TradingMandate).count()

    outcomes: list[str] = []

    def approve(index: int) -> None:
        with pg_sessionmaker() as session:
            admin = session.get(User, admin_ids[index])
            try:
                mandate_proposals.approve(session, admin, proposal_id, note=f"second {index}")
                outcomes.append("applied")
            except mandate_proposals.ProposalConflict:
                outcomes.append("conflict")

    errors = _run(3, approve)
    assert not errors, errors
    assert sorted(outcomes) == ["applied", "conflict", "conflict"]
    with pg_sessionmaker() as session:
        assert session.query(TradingMandate).count() == mandates_before + 1
        row = session.get(TradingMandateProposal, proposal_id)
        assert row.status == "applied" and len(row.approvals_json) == 2
