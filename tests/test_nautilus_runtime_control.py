from __future__ import annotations

import sys
from types import ModuleType
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.services.strategy_control_service import (
    StrategyControlError,
    activate_strategy,
    create_strategy,
    modify_strategy,
    preview_activation,
)
from apps.api.services.trading_service import (
    TradingServiceError,
    confirm_order,
    preview_order,
    reconcile_account,
)
from packages.agents.chat.tools import AgentToolRegistry
from packages.database.models import (
    CreditReservationRecord,
    OrderJournal,
    SignalEvent,
    StrategyRun,
    TradingAccount,
    TradingAuditLog,
)
from packages.trading.runtime_client import RuntimeUnavailable
from packages.trading.policies.safety import (
    LiveExecutionDenied,
    assert_execution_mode_allowed,
)
from packages.trading.states.order_state import InvalidOrderTransition, transition_order
from tests.conftest import auth_headers


RUNTIME_ROOT = Path(__file__).parents[1] / "services" / "nautilus-runtime"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from app import main as runtime_main  # noqa: E402
from app.nautilus_bridge import NautilusCoreBridge  # noqa: E402
from app.runtime_manager import RuntimeManager  # noqa: E402
from app.state_store import RuntimeStateStore  # noqa: E402


class FakeRuntime:
    def __init__(self):
        self.calls = []

    def command(self, command_type, idempotency_key, payload):
        self.calls.append((command_type, idempotency_key, payload))
        if command_type == "activate":
            return {
                "status": "RUNNING",
                "command_id": "cmd-activate",
                "id": payload["run_id"],
                **payload,
            }
        if command_type == "submit_order":
            return {
                "state": "ACCEPTED",
                "command_id": "cmd-order",
                "sequence": 5,
                "exchange_order_id": "mock-order",
                "filled_quantity": 0,
                "remaining_quantity": payload["quantity"],
                "risk_decision": {
                    "decision": "ALLOW",
                    "reasons": [],
                    "limits": {},
                    "state": {},
                },
            }
        return {"status": "RECONCILED", "command_id": "cmd-other"}


class UnavailableRuntime:
    def command(self, command_type, idempotency_key, payload):
        raise RuntimeUnavailable("test runtime unavailable")


def test_native_nautilus_bridge_initializes_and_publishes(monkeypatch):
    published = []

    class FakeMessageBus:
        def __init__(self, trader_id, clock):
            self.trader_id = trader_id
            self.clock = clock

        def publish(self, *, topic, msg):
            published.append((topic, msg))

    class FakeTraderId(str):
        pass

    package = ModuleType("nautilus_trader")
    package.__version__ = "test-native"
    common = ModuleType("nautilus_trader.common")
    component = ModuleType("nautilus_trader.common.component")
    component.MessageBus = FakeMessageBus
    component.TestClock = object
    model = ModuleType("nautilus_trader.model")
    identifiers = ModuleType("nautilus_trader.model.identifiers")
    identifiers.TraderId = FakeTraderId
    for name, value in {
        "nautilus_trader": package,
        "nautilus_trader.common": common,
        "nautilus_trader.common.component": component,
        "nautilus_trader.model": model,
        "nautilus_trader.model.identifiers": identifiers,
    }.items():
        monkeypatch.setitem(sys.modules, name, value)

    bridge = NautilusCoreBridge()
    bridge.publish("puregamma.runtime.run_started", {"run_id": "run-native"})

    assert bridge.status()["available"] is True
    assert bridge.status()["version"] == "test-native"
    assert published == [("puregamma.runtime.run_started", {"run_id": "run-native"})]


def paper_account(db, user):
    row = TradingAccount(
        user_id=user.id,
        name="Test Paper",
        venue="MOCK",
        account_type="PAPER",
        status="ACTIVE",
        permissions_json={
            "paper_order": True,
            "shadow_order": True,
            "live_order": False,
            "withdraw": False,
            "transfer": False,
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def draft(name="BTC trend"):
    return {
        "name": name,
        "description": "test",
        "instruments": ["BTCUSDT"],
        "venues": ["MOCK"],
        "timeframe": "1h",
        "strategy_type": "trend",
        "entry_rules": [{"type": "momentum"}],
        "exit_rules": [{"type": "stop"}],
        "sentiment_sources": ["rss", "fintwit", "x-twitter", "bloomberg"],
        "execution_mode": "PAPER",
    }


def test_live_execution_is_compiled_out(monkeypatch):
    assert_execution_mode_allowed("PAPER")
    with pytest.raises(LiveExecutionDenied):
        assert_execution_mode_allowed("LIVE")
    monkeypatch.setenv("NAUTILUS_ALLOW_LIVE_ORDER", "true")
    with pytest.raises(LiveExecutionDenied):
        assert_execution_mode_allowed("PAPER")


def test_order_state_machine_rejects_invalid_transition():
    assert transition_order("CREATED", "PREPARED").value == "PREPARED"
    with pytest.raises(InvalidOrderTransition):
        transition_order("CREATED", "FILLED")


def test_runtime_activation_is_idempotent_and_live_denied(tmp_path):
    runtime_main.manager = RuntimeManager(str(tmp_path / "runtime.sqlite3"))
    client = TestClient(runtime_main.app)
    headers = {"X-PG-Runtime-Secret": "dev-runtime-secret"}
    command = {
        "idempotency_key": "activation-idempotency",
        "payload": {
            "run_id": "run-1",
            "strategy_id": "strategy-1",
            "strategy_version": 1,
            "account_id": "paper-1",
            "mode": "PAPER",
            "strategy": {"name": "test"},
        },
    }
    first = client.post("/commands/activate", json=command, headers=headers)
    second = client.post("/commands/activate", json=command, headers=headers)
    assert first.status_code == 200 and first.json()["status"] == "RUNNING"
    assert second.json()["idempotent"] is True
    live = client.post(
        "/commands/activate",
        json={
            **command,
            "idempotency_key": "activation-live",
            "payload": {**command["payload"], "mode": "LIVE"},
        },
        headers=headers,
    )
    assert live.status_code == 403
    assert client.get("/runs").status_code == 401


def test_runtime_order_journal_risk_and_cancel(tmp_path):
    manager = RuntimeManager(str(tmp_path / "runtime.sqlite3"))
    base = {
        "account_id": "paper",
        "instrument": "BTCUSDT",
        "venue": "MOCK",
        "direction": "BUY",
        "side": "BUY",
        "quantity": 0.1,
        "notional": 1000,
        "leverage": 1,
        "order_type": "MARKET",
        "reduce_only": False,
        "mode": "PAPER",
        "risk_policy": {
            "max_position": 1,
            "max_notional": 5000,
            "max_leverage": 2,
            "max_orders_per_minute": 5,
        },
        "idempotency_key": "order-one",
    }
    accepted = manager.command("submit_order", "command-order-one", base)
    assert accepted["state"] == "ACCEPTED"
    assert (
        manager.command("submit_order", "command-order-one", base)["idempotent"] is True
    )
    assert manager.store.latest_order(accepted["client_order_id"])["sequence"] == 5
    canceled = manager.command(
        "cancel_order",
        "cancel-order-one",
        {"account_id": "paper", "client_order_id": accepted["client_order_id"]},
    )
    assert canceled["state"] == "CANCELED"
    rejected = manager.command(
        "submit_order",
        "command-order-large",
        {**base, "idempotency_key": "order-large", "notional": 100_000},
    )
    assert rejected["state"] == "REJECTED"
    assert "MAX_NOTIONAL" in rejected["risk_decision"]["reasons"]


def test_runtime_restart_marks_uncertain_orders_for_reconciliation(tmp_path):
    path = str(tmp_path / "runtime.sqlite3")
    store = RuntimeStateStore(path)
    store.append_order(
        {
            "client_order_id": "uncertain",
            "sequence": 1,
            "idempotency_key": "uncertain-1",
            "account_id": "paper",
            "state": "SUBMITTING",
            "quantity": 1,
            "remaining_quantity": 1,
        }
    )
    manager = RuntimeManager(path)
    assert manager.recovered_orders == 1
    assert manager.store.latest_order("uncertain")["state"] == "RECONCILIATION_REQUIRED"


def test_strategy_preview_requires_separate_exact_confirmation(db, max_user):
    account = paper_account(db, max_user)
    strategy = create_strategy(
        db, max_user.id, draft(), idempotency_key="create-safe-strategy"
    )
    intent, phrase = preview_activation(
        db,
        max_user.id,
        strategy.id,
        mode="PAPER",
        account_id=account.id,
        conversation_id=None,
        idempotency_key="preview-safe-strategy",
    )
    assert strategy.status == "DRAFT"
    assert db.query(StrategyRun).filter_by(strategy_id=strategy.id).count() == 0
    with pytest.raises(StrategyControlError):
        activate_strategy(
            db, max_user.id, strategy.id, intent.id, "好的", runtime=FakeRuntime()
        )
    runtime = FakeRuntime()
    activation, run = activate_strategy(
        db, max_user.id, strategy.id, intent.id, phrase, runtime=runtime
    )
    assert activation.status == "RUNNING" and run.status == "RUNNING"
    assert runtime.calls[0][0] == "activate"
    assert db.query(SignalEvent).filter_by(run_id=run.id).count() == 1
    assert (
        db.query(TradingAuditLog)
        .filter_by(action="ACTIVATE_STRATEGY", strategy_id=strategy.id)
        .count()
        == 1
    )


def test_strategy_activation_runtime_failure_refunds_persisted_reservation(db, max_user):
    account = paper_account(db, max_user)
    strategy = create_strategy(
        db, max_user.id, draft("Refund activation"), idempotency_key="create-refund-strategy"
    )
    intent, phrase = preview_activation(
        db,
        max_user.id,
        strategy.id,
        mode="PAPER",
        account_id=account.id,
        conversation_id=None,
        idempotency_key="preview-refund-strategy",
    )
    balance_before = max_user.credit_balance

    with pytest.raises(RuntimeUnavailable):
        activate_strategy(
            db, max_user.id, strategy.id, intent.id, phrase, runtime=UnavailableRuntime()
        )
    db.refresh(max_user)

    assert max_user.credit_balance == balance_before
    reservation = db.query(CreditReservationRecord).filter_by(idempotency_key=f"strategy-activation-charge:{intent.id}").one()
    assert reservation.status == "REFUNDED"


def test_runtime_reconciliation_is_platform_funded(db, max_user):
    account = paper_account(db, max_user)
    max_user.credit_balance = 0
    db.commit()

    record = reconcile_account(db, max_user.id, account.id, runtime=FakeRuntime())
    db.refresh(max_user)

    assert record.status == "RECONCILED"
    assert max_user.credit_balance == 0


def test_strategy_change_invalidates_old_confirmation(db, max_user):
    account = paper_account(db, max_user)
    strategy = create_strategy(
        db, max_user.id, draft(), idempotency_key="create-changing-strategy"
    )
    intent, phrase = preview_activation(
        db,
        max_user.id,
        strategy.id,
        mode="PAPER",
        account_id=account.id,
        conversation_id=None,
        idempotency_key="preview-changing-strategy",
    )
    modify_strategy(
        db,
        max_user.id,
        strategy.id,
        {"max_notional": 2000},
        idempotency_key="modify-changing-strategy",
    )
    with pytest.raises(StrategyControlError):
        activate_strategy(
            db, max_user.id, strategy.id, intent.id, phrase, runtime=FakeRuntime()
        )
    db.refresh(intent)
    assert intent.approval_status == "INVALIDATED"


def test_manual_order_is_preview_then_confirm(db, max_user):
    account = paper_account(db, max_user)
    intent, phrase = preview_order(
        db,
        max_user.id,
        {
            "account_id": account.id,
            "instrument": "BTCUSDT",
            "direction": "BUY",
            "quantity": 0.1,
            "notional": 1000,
            "leverage": 1,
            "execution_mode": "PAPER",
            "idempotency_key": "manual-order-preview",
        },
    )
    assert db.query(OrderJournal).count() == 0
    with pytest.raises(TradingServiceError):
        confirm_order(db, max_user.id, intent.id, "继续", runtime=FakeRuntime())
    journal = confirm_order(db, max_user.id, intent.id, phrase, runtime=FakeRuntime())
    assert journal.state == "ACCEPTED"
    assert db.query(OrderJournal).count() == 1


def test_strategy_api_tenant_isolation_and_live_denial(
    api_client, db, max_user, pro_user
):
    paper_account(db, max_user)
    response = api_client.post(
        "/strategies",
        json={"draft": draft()},
        headers={**auth_headers(max_user), "Idempotency-Key": "api-create-strategy"},
    )
    assert response.status_code == 200
    strategy_id = response.json()["strategy"]["id"]
    assert (
        api_client.get(
            f"/strategies/{strategy_id}", headers=auth_headers(pro_user)
        ).status_code
        == 404
    )
    live = api_client.post(
        f"/strategies/{strategy_id}/preview-activation",
        json={"mode": "LIVE"},
        headers=auth_headers(max_user),
    )
    assert live.status_code == 400


def test_runtime_events_are_filtered_by_owned_run(
    api_client, db, max_user, monkeypatch
):
    strategy = create_strategy(
        db, max_user.id, draft(), idempotency_key="events-owned-strategy"
    )
    run = StrategyRun(
        user_id=max_user.id,
        strategy_id=strategy.id,
        strategy_version=1,
        runtime_run_id="owned-runtime-run",
        execution_mode="PAPER",
        status="RUNNING",
    )
    db.add(run)
    db.commit()

    monkeypatch.setattr(
        "packages.trading.runtime_client.NautilusRuntimeClient.events",
        lambda self, limit=100: {
            "events": [
                {
                    "id": 1,
                    "event_type": "STRATEGY_SIGNAL",
                    "aggregate_id": "owned-runtime-run",
                    "payload": {"run_id": "owned-runtime-run"},
                    "created_at": "2026-07-11T00:00:00+00:00",
                },
                {
                    "id": 2,
                    "event_type": "STRATEGY_SIGNAL",
                    "aggregate_id": "other-user-run",
                    "payload": {"run_id": "other-user-run"},
                    "created_at": "2026-07-11T00:00:00+00:00",
                },
            ]
        },
    )

    response = api_client.get("/trading/runtime/events", headers=auth_headers(max_user))

    assert response.status_code == 200
    assert [event["aggregate_id"] for event in response.json()["events"]] == [
        "owned-runtime-run"
    ]


def test_agent_start_language_only_builds_preview_plan(db, max_user):
    registry = AgentToolRegistry(db, max_user.id)
    assert registry.plan("启动这个策略") == [
        ("preview_strategy_activation", {"mode": "PAPER"})
    ]
    assert registry.plan("好的") == []
    assert (
        registry.plan("CONFIRM STRATEGY abc VERSION 1 token")[0][0]
        == "activate_strategy"
    )
