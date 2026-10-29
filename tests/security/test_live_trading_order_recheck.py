"""UNKNOWN order sync status and the owner's "re-check" request.

Pins: a re-check only ever QUERIES the venue (``submit_order`` and
``cancel_order`` are never called and no order/intent row is created), it is
rate-limited per order, owner-scoped (another user's order is a 404), off by
default, allowed under a kill switch, and every answer is audited.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest

from apps.api.config import get_settings
from packages.database.models import Fill, LedgerEntry, LiveOrder, LiveOrderIntent, TradingAuditLog
from packages.live_trading import control_plane, kill_switch, order_sync
from packages.live_trading.gateway_adapter import GatewayOrderUnknown
from tests.conftest import auth_headers
from tests.security.test_live_trading_foundation import _make_fill_order, _make_live_world


class SpyGateway:
    """Answers queries from a script; any submit or cancel fails the test."""

    name = "spy"

    def __init__(self, answers=None):
        self.answers = list(answers or [{"state": "unknown", "reason": "not visible yet"}])
        self.queries: list[str] = []
        self.submitted: list[dict] = []
        self.canceled: list[str] = []

    def submit_order(self, payload):  # pragma: no cover - asserted never called
        self.submitted.append(payload)
        raise AssertionError("a re-check must never submit")

    def cancel_order(self, client_order_id, account_id, *, connection_id=None, symbol=None):  # pragma: no cover
        self.canceled.append(client_order_id)
        raise AssertionError("a re-check must never cancel")

    def query_order(self, client_order_id, account_id, *, connection_id=None, symbol=None):
        self.queries.append(client_order_id)
        answer = self.answers[min(len(self.queries), len(self.answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer


def _settings(monkeypatch, **overrides):
    settings = dataclasses.replace(get_settings(), **overrides)
    monkeypatch.setattr(order_sync, "get_settings", lambda: settings)
    return settings


def _unknown_order(db, user, monkeypatch):
    world = _make_live_world(db, user, monkeypatch)
    order = _make_fill_order(db, user, world, side="buy", quantity="0.5")
    order.status = "unknown"
    order.error_code = "SUBMIT_UNKNOWN"
    db.commit()
    return world, order


def _install(monkeypatch, gateway):
    monkeypatch.setattr(control_plane, "get_execution_gateway", lambda: gateway)
    return gateway


def _audit(db, action):
    return db.query(TradingAuditLog).filter_by(action=action).order_by(TradingAuditLog.created_at.asc()).all()


def test_recheck_is_off_by_default(api_client, db, user_factory, monkeypatch):
    assert get_settings().live_order_recheck_enabled is False
    user = user_factory("recheck-off@test.com")
    _, order = _unknown_order(db, user, monkeypatch)
    gateway = _install(monkeypatch, SpyGateway())
    response = api_client.post(f"/api/trading/orders/{order.id}/recheck", headers=auth_headers(user))
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "LIVE_ORDER_RECHECK_DISABLED"
    assert gateway.queries == [] and _audit(db, order_sync.RECHECK_ACTION) == []
    status = api_client.get(f"/api/trading/orders/{order.id}/sync-status", headers=auth_headers(user)).json()["sync"]
    assert status["recheck"] == {
        "enabled": False, "allowed": False, "blocked_reason": "disabled",
        "min_interval_seconds": 60, "next_allowed_at": None,
    }


def test_recheck_only_queries_and_never_creates_an_order(api_client, db, user_factory, monkeypatch):
    _settings(monkeypatch, live_order_recheck_enabled=True)
    user = user_factory("recheck-query@test.com")
    _, order = _unknown_order(db, user, monkeypatch)
    gateway = _install(monkeypatch, SpyGateway())
    orders_before, intents_before = db.query(LiveOrder).count(), db.query(LiveOrderIntent).count()

    response = api_client.post(f"/api/trading/orders/{order.id}/recheck", headers=auth_headers(user))
    assert response.status_code == 200, response.text
    sync = response.json()["sync"]
    assert gateway.queries == [order.client_order_id]
    assert gateway.submitted == [] and gateway.canceled == []
    assert db.query(LiveOrder).count() == orders_before
    assert db.query(LiveOrderIntent).count() == intents_before
    assert sync["status"] == "unknown"
    assert sync["latest"]["outcome"] == "still_unknown"
    assert sync["latest"]["reason"] == "not visible yet"
    assert sync["latest"]["trigger"] == "user_recheck"
    assert sync["last_sync_at"] is not None
    # Both the request and its answer are on the audit trail.
    requested = _audit(db, order_sync.RECHECK_ACTION)
    assert len(requested) == 1 and requested[0].actor_type == "user"
    assert requested[0].request_json["order_id"] == order.id
    assert len(_audit(db, order_sync.SYNC_ACTION)) == 1


def test_a_failed_query_is_reported_with_its_reason_and_keeps_unknown(api_client, db, user_factory, monkeypatch):
    _settings(monkeypatch, live_order_recheck_enabled=True)
    user = user_factory("recheck-fail@test.com")
    _, order = _unknown_order(db, user, monkeypatch)
    gateway = _install(monkeypatch, SpyGateway([GatewayOrderUnknown("venue timeout after 8s")]))
    sync = api_client.post(f"/api/trading/orders/{order.id}/recheck", headers=auth_headers(user)).json()["sync"]
    assert sync["status"] == "unknown"
    assert sync["latest"]["outcome"] == "query_failed"
    assert "venue timeout" in sync["latest"]["reason"]
    assert gateway.submitted == []


def test_a_definite_answer_resolves_the_order_and_books_the_fill_once(api_client, db, user_factory, monkeypatch):
    _settings(monkeypatch, live_order_recheck_enabled=True, live_order_recheck_min_interval_seconds=10)
    user = user_factory("recheck-fill@test.com")
    _, order = _unknown_order(db, user, monkeypatch)
    filled = {"state": "filled", "order": {"broker_order_id": "brk-1", "fills": [{"broker_fill_id": "bf-1", "quantity": "0.5", "price": "100", "fee": "0"}]}}
    gateway = _install(monkeypatch, SpyGateway([filled]))
    sync = api_client.post(f"/api/trading/orders/{order.id}/recheck", headers=auth_headers(user)).json()["sync"]
    assert sync["status"] == "filled"
    assert sync["latest"] == {**sync["latest"], "outcome": "resolved", "state_before": "unknown", "state_after": "filled"}
    assert sync["recheck"]["blocked_reason"] == "terminal"
    assert db.query(Fill).count() == 1
    assert db.query(LedgerEntry).filter_by(entry_type="trade_buy").count() == 1
    assert gateway.submitted == []
    # A final order cannot be re-checked.
    again = api_client.post(f"/api/trading/orders/{order.id}/recheck", headers=auth_headers(user))
    assert again.status_code == 409
    assert gateway.queries == [order.client_order_id]


def test_recheck_is_rate_limited_per_order(api_client, db, user_factory, monkeypatch):
    _settings(monkeypatch, live_order_recheck_enabled=True, live_order_recheck_min_interval_seconds=60)
    user = user_factory("recheck-rate@test.com")
    world, order = _unknown_order(db, user, monkeypatch)
    gateway = _install(monkeypatch, SpyGateway())
    assert api_client.post(f"/api/trading/orders/{order.id}/recheck", headers=auth_headers(user)).status_code == 200

    limited = api_client.post(f"/api/trading/orders/{order.id}/recheck", headers=auth_headers(user))
    assert limited.status_code == 429
    assert limited.json()["detail"]["code"] == "LIVE_ORDER_RECHECK_RATE_LIMITED"
    assert 1 <= int(limited.headers["Retry-After"]) <= 61
    assert gateway.queries == [order.client_order_id]
    assert len(_audit(db, order_sync.RECHECK_ACTION)) == 1
    status = api_client.get(f"/api/trading/orders/{order.id}/sync-status", headers=auth_headers(user)).json()["sync"]
    assert status["recheck"]["blocked_reason"] == "rate_limited" and status["recheck"]["next_allowed_at"]

    # The limit is per order: another open order of the same user is not blocked.
    other = _make_fill_order(db, user, world, side="sell", quantity="0.1")
    assert api_client.post(f"/api/trading/orders/{other.id}/recheck", headers=auth_headers(user)).status_code == 200

    # Once the interval has passed the same order may be asked again.
    for row in _audit(db, order_sync.RECHECK_ACTION):
        row.created_at = row.created_at - timedelta(seconds=61)
    db.commit()
    assert api_client.post(f"/api/trading/orders/{order.id}/recheck", headers=auth_headers(user)).status_code == 200
    assert gateway.queries.count(order.client_order_id) == 2


def test_another_users_order_is_a_404_for_status_and_recheck(api_client, db, user_factory, monkeypatch):
    _settings(monkeypatch, live_order_recheck_enabled=True)
    alice = user_factory("recheck-alice@test.com")
    bob = user_factory("recheck-bob@test.com")
    _, order = _unknown_order(db, alice, monkeypatch)
    gateway = _install(monkeypatch, SpyGateway())
    for method, path in (("get", "sync-status"), ("post", "recheck")):
        foreign = getattr(api_client, method)(f"/api/trading/orders/{order.id}/{path}", headers=auth_headers(bob))
        missing = getattr(api_client, method)(f"/api/trading/orders/no-such-order/{path}", headers=auth_headers(bob))
        assert foreign.status_code == missing.status_code == 404, path
        assert foreign.json() == missing.json()
    assert gateway.queries == []
    assert _audit(db, order_sync.RECHECK_ACTION) == []


def test_recheck_still_works_while_a_kill_switch_is_engaged(api_client, db, user_factory, monkeypatch):
    _settings(monkeypatch, live_order_recheck_enabled=True)
    user = user_factory("recheck-kill@test.com")
    _, order = _unknown_order(db, user, monkeypatch)
    kill_switch.engage(db, scope="global", reason="incident")
    db.commit()
    gateway = _install(monkeypatch, SpyGateway())
    response = api_client.post(f"/api/trading/orders/{order.id}/recheck", headers=auth_headers(user))
    assert response.status_code == 200
    assert gateway.queries == [order.client_order_id] and gateway.submitted == []


def test_background_sync_records_only_changed_answers(db, user_factory, monkeypatch):
    user = user_factory("recheck-bg@test.com")
    _, order = _unknown_order(db, user, monkeypatch)
    same = {"state": "unknown", "reason": "not visible yet"}
    gateway = SpyGateway([same, same, same, GatewayOrderUnknown("timeout")])
    for _ in range(4):
        control_plane.sync_order_status(db, order, gateway=gateway)
    rows = _audit(db, order_sync.SYNC_ACTION)
    assert [row.result_json["outcome"] for row in rows] == ["still_unknown", "query_failed"]
    assert all(row.actor_type == "system" for row in rows)
    assert len(gateway.queries) == 4 and gateway.submitted == []


@pytest.mark.parametrize("terminal", ["filled", "canceled", "rejected", "expired"])
def test_final_orders_are_never_queried(db, user_factory, monkeypatch, terminal):
    user = user_factory(f"recheck-final-{terminal}@test.com")
    _, order = _unknown_order(db, user, monkeypatch)
    order.status = terminal
    db.commit()
    gateway = SpyGateway()
    control_plane.sync_order_status(db, order, gateway=gateway)
    assert gateway.queries == [] and _audit(db, order_sync.SYNC_ACTION) == []


def test_a_failed_audit_write_rolls_the_whole_sync_back_and_the_next_tick_retries(db, user_factory, monkeypatch):
    """The sync result is written in the same transaction as the order state.
    If the audit insert fails, nothing of that sync is kept (no state change,
    no fill, no ledger row) — exactly as if the venue had not been asked —
    and the next background tick queries again. Nothing is ever submitted."""
    user = user_factory("recheck-auditfail@test.com")
    _, order = _unknown_order(db, user, monkeypatch)
    filled = {"state": "filled", "order": {"broker_order_id": "brk-9", "fills": [{"broker_fill_id": "bf-9", "quantity": "0.5", "price": "100", "fee": "0"}]}}
    gateway = SpyGateway([filled, filled])
    real = order_sync.record_sync_result

    def broken(*args, **kwargs):
        raise RuntimeError("audit table unavailable")

    monkeypatch.setattr(order_sync, "record_sync_result", broken)
    with pytest.raises(RuntimeError):
        control_plane.sync_order_status(db, order, gateway=gateway)
    db.rollback()  # what packages.workers.tasks.sync_live_order_statuses does per order
    db.expire_all()
    assert db.get(LiveOrder, order.id).status == "unknown"
    assert db.query(Fill).count() == 0 and db.query(LedgerEntry).count() == 0

    monkeypatch.setattr(order_sync, "record_sync_result", real)
    control_plane.sync_order_status(db, db.get(LiveOrder, order.id), gateway=gateway)
    assert db.get(LiveOrder, order.id).status == "filled"
    assert db.query(Fill).count() == 1 and db.query(LedgerEntry).filter_by(entry_type="trade_buy").count() == 1
    assert len(gateway.queries) == 2 and gateway.submitted == []
