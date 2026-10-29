"""Deterministic replay and race cases for the LIVE control plane (SQLite).

The threaded versions run against Postgres in
``test_live_trading_concurrency_postgres``; these pin the same properties
without a database server by injecting the competing write at the exact
point a concurrent request would land.
"""

from __future__ import annotations

from packages.database.models import LiveOrder, LiveOrderIntent, TradingAuditLog
from packages.live_trading import control_plane, kill_switch, risk_engine
from packages.live_trading.enums import LiveOrderStatus
from packages.live_trading.gateway_adapter import GatewayUnavailable
from tests.security.test_live_trading_foundation import FakeGateway, _make_fill_order, _make_live_world


def _preview(db, user, world, gateway):
    result = control_plane.preview_order(
        db, user.id, mandate_id=world["mandate"].id, symbol="BTCUSDT", side="buy", quantity="0.5", gateway=gateway
    )
    return result["intent"], result["confirmation"]


def test_replay_of_one_intent_never_submits_twice(db, user_factory, monkeypatch):
    user = user_factory("race-replay@test.com")
    world = _make_live_world(db, user, monkeypatch)
    gateway = FakeGateway()
    intent, phrase = _preview(db, user, world, gateway)
    first = control_plane.confirm_order(db, user.id, order_intent_id=intent.id, confirmation=phrase, gateway=gateway)
    for _ in range(3):
        again = control_plane.confirm_order(db, user.id, order_intent_id=intent.id, confirmation=phrase, gateway=gateway)
        assert again.id == first.id
    assert len(gateway.submitted) == 1
    assert db.query(LiveOrder).filter_by(client_order_id=first.client_order_id).count() == 1


def test_replay_after_an_unknown_submit_is_the_same_order_and_never_resubmits(db, user_factory, monkeypatch):
    user = user_factory("race-unknown@test.com")
    world = _make_live_world(db, user, monkeypatch)

    class TimeoutGateway(FakeGateway):
        def submit_order(self, payload):
            self.submitted.append(payload)
            from packages.live_trading.gateway_adapter import GatewayOrderUnknown

            raise GatewayOrderUnknown("submit timed out")

    gateway = TimeoutGateway()
    intent, phrase = _preview(db, user, world, gateway)
    order = control_plane.confirm_order(db, user.id, order_intent_id=intent.id, confirmation=phrase, gateway=gateway)
    assert order.status == LiveOrderStatus.UNKNOWN.value
    replay = control_plane.confirm_order(db, user.id, order_intent_id=intent.id, confirmation=phrase, gateway=gateway)
    assert replay.id == order.id and len(gateway.submitted) == 1


def test_a_confirm_that_loses_the_race_returns_the_winners_order(db, user_factory, monkeypatch):
    """Two confirms of one intent: the loser waited on the mandate lock while
    the winner committed its order. The loser must answer with that order —
    not re-run risk (which could now reject and flip the intent to REJECTED),
    and never submit."""
    user = user_factory("race-loser@test.com")
    world = _make_live_world(db, user, monkeypatch)
    gateway = FakeGateway()
    intent, phrase = _preview(db, user, world, gateway)
    original = control_plane.owned_mandate

    def winner_commits_while_we_wait(db_, user_id, mandate_id, *, lock=False):
        if lock:
            winner = LiveOrder(
                user_id=user_id, mandate_id=mandate_id, order_intent_id=intent.id, symbol="BTCUSDT", side="buy",
                quantity=intent.quantity, order_type="market", status="submitted", client_order_id=intent.client_order_id,
                idempotency_key=f"order:{intent.idempotency_key}", trace_id=intent.trace_id,
            )
            db_.add(winner)
            db_.query(LiveOrderIntent).filter_by(id=intent.id).update({"status": "APPROVED"})
            db_.commit()
        return original(db_, user_id, mandate_id, lock=lock)

    monkeypatch.setattr(control_plane, "owned_mandate", winner_commits_while_we_wait)
    rejecting = risk_engine.RiskEngine.evaluate

    def reject_everything(self, **kwargs):
        verdict = rejecting(self, **kwargs)
        verdict.result, verdict.rejection_reason = "REJECT", "MAX_POSITION"
        return verdict

    monkeypatch.setattr(risk_engine.RiskEngine, "evaluate", reject_everything)
    result = control_plane.confirm_order(db, user.id, order_intent_id=intent.id, confirmation=phrase, gateway=gateway)
    assert result.client_order_id == intent.client_order_id
    assert gateway.submitted == []
    db.expire_all()
    assert db.get(LiveOrderIntent, intent.id).status == "APPROVED"
    assert db.query(LiveOrder).filter_by(order_intent_id=intent.id).count() == 1


def test_pause_and_resume_in_the_same_second_are_each_audited(db, user_factory, monkeypatch):
    user = user_factory("race-pause@test.com")
    world = _make_live_world(db, user, monkeypatch)
    mandate_id = world["mandate"].id
    for _ in range(3):
        control_plane.pause_mandate(db, user.id, mandate_id, reason="pause")
        control_plane.resume_mandate(db, user.id, mandate_id, confirmation=f"RESUME {mandate_id}")
    actions = [row.action for row in db.query(TradingAuditLog).filter(TradingAuditLog.action.like("LIVE_MANDATE_%")).order_by(TradingAuditLog.created_at, TradingAuditLog.id).all()]
    assert actions.count("LIVE_MANDATE_PAUSE") == 3
    assert actions.count("LIVE_MANDATE_RESUME") == 3


def test_a_retried_cancel_is_audited_and_clears_its_failure(db, user_factory, monkeypatch):
    user = user_factory("race-cancel@test.com")
    world = _make_live_world(db, user, monkeypatch)
    order = _make_fill_order(db, user, world, side="buy", quantity="0.5")

    class FlakyCancel(FakeGateway):
        calls = 0

        def cancel_order(self, client_order_id, account_id, *, connection_id=None, symbol=None):
            FlakyCancel.calls += 1
            if FlakyCancel.calls == 1:
                raise GatewayUnavailable("venue timeout")
            return {"state": "canceled"}

    gateway = FlakyCancel()
    failed = control_plane.cancel_order(db, user.id, order.client_order_id, gateway=gateway)
    assert failed.status == "submitted" and failed.error_code == "CANCEL_UNKNOWN"
    done = control_plane.cancel_order(db, user.id, order.client_order_id, gateway=gateway)
    assert done.status == "canceled" and done.error_code is None
    audits = db.query(TradingAuditLog).filter_by(action="LIVE_ORDER_CANCEL").order_by(TradingAuditLog.created_at).all()
    assert [row.status for row in audits] == ["submitted", "canceled"]
    assert audits[0].result_json["error_code"] == "CANCEL_UNKNOWN"


def test_a_kill_switch_does_not_block_or_swallow_a_cancel(db, user_factory, monkeypatch):
    user = user_factory("race-kill-cancel@test.com")
    world = _make_live_world(db, user, monkeypatch)
    order = _make_fill_order(db, user, world, side="buy", quantity="0.5")
    for scope, scope_id in (("global", None), ("user", user.id), ("mandate", world["mandate"].id), ("connection", world["connection"].id)):
        kill_switch.engage(db, scope=scope, scope_id=scope_id, reason="incident")
    db.commit()
    canceled = control_plane.cancel_order(db, user.id, order.client_order_id, gateway=FakeGateway())
    assert canceled.status == "canceled"
    assert db.query(TradingAuditLog).filter_by(action="LIVE_ORDER_CANCEL", status="canceled").count() == 1
