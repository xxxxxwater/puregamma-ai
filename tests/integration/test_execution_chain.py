from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from packages.database.models import StrategyRun, TradingAccount
from packages.trading.states.order_state import transition_order
from tests.conftest import auth_headers


RUNTIME_ROOT = Path(__file__).parents[2] / "services" / "nautilus-runtime"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from app import main as runtime_main  # noqa: E402
from app.runtime_manager import RuntimeManager  # noqa: E402

from apps.api.services.strategy_control_service import run_strategy_backtest  # noqa: E402


class SequentialMarketData:
    def __init__(self, prices):
        self.prices = iter(prices)

    def fetch(self, symbols, force=False):
        price = next(self.prices)
        quote = {
            "asset": "BTC",
            "symbol": "BTCUSDT",
            "price": price,
            "provider": "test_public",
            "timestamp": f"2026-07-20T00:00:{int(price) % 60:02d}+00:00",
            "stale": False,
        }
        return {
            "quotes": [quote],
            "missing": [],
            "errors": [],
            "providers": [],
            "fetchedAt": quote["timestamp"],
            "liveOrders": False,
        }

    def status(self):
        return []


class FakeBinanceAdapter:
    """Recorded Binance testnet stand-in: book/price data only, never submits."""

    name = "binance_spot_testnet"

    def __init__(self):
        self.book = {
            "symbol": "BTCUSDT",
            "bids": [[59900.0, 0.5]],
            "asks": [[60500.0, 0.01], [60600.0, 1.0]],
        }
        self.book_calls = 0
        self.submit_calls = 0

    def health_check(self):
        return {"status": "HEALTHY", "adapter": self.name, "live": False}

    def fetch_order_book(self, symbol, limit=20):
        self.book_calls += 1
        return self.book

    def fetch_price(self, symbol):
        return {"symbol": symbol, "price": 60600.0, "provider": self.name}

    def submit_order(self, order):  # pragma: no cover - must never be called
        self.submit_calls += 1
        raise AssertionError("SHADOW mode must never submit to the real adapter")


def activate(manager: RuntimeManager, run_id: str, mode: str, account=None):
    payload = {
        "run_id": run_id,
        "strategy_id": f"strategy-{run_id}",
        "strategy_version": 1,
        "account_id": f"acct-{run_id}",
        "mode": mode,
        "strategy": {
            "name": "BTC momentum",
            "instruments": ["BTCUSDT"],
            "entry_rules": [{"threshold": 0.001}],
            "max_notional": 1000,
            "max_position": 1,
            "leverage": 1,
        },
        "risk_policy": {
            "max_notional": 1000,
            "max_position": 1,
            "max_leverage": 1,
            "max_orders_per_minute": 10,
        },
    }
    if account:
        payload["account"] = account
    return manager.command("activate", f"activation-{run_id}", payload)


def base_order(run_id: str, account_id: str, **overrides) -> dict:
    order = {
        "account_id": account_id,
        "run_id": run_id,
        "instrument": "BTCUSDT",
        "venue": "MOCK",
        "direction": "BUY",
        "side": "BUY",
        "quantity": 0.01,
        "notional": 600,
        "leverage": 1,
        "order_type": "MARKET",
        "reduce_only": False,
        "mode": "PAPER",
        "risk_policy": {
            "max_notional": 5000,
            "max_position": 1,
            "max_leverage": 2,
            "max_orders_per_minute": 10,
        },
        "idempotency_key": f"order-{run_id}",
    }
    return {**order, **overrides}


def assert_journal_legal(manager: RuntimeManager, client_order_id: str) -> list[dict]:
    journal = manager.store.order_journal(client_order_id)
    assert journal, "expected a journaled order"
    for previous, current in zip(journal, journal[1:]):
        transition_order(previous["state"], current["state"])
    return journal


def assert_all_journals_legal(manager: RuntimeManager) -> None:
    for order in manager.store.latest_orders():
        assert_journal_legal(manager, order["client_order_id"])


# ------------------------------------------------------------- full chain


def test_full_chain_mock_signal_risk_intent_fill_position_pnl_reconcile(tmp_path):
    manager = RuntimeManager(str(tmp_path / "chain.sqlite3"))
    manager.market_data = SequentialMarketData([60000, 60600, 61200])
    activate(manager, "run-chain", "PAPER")

    assert manager.refresh_market_data(["BTCUSDT"], force=True)["signals"] == []
    result = manager.refresh_market_data(["BTCUSDT"], force=True)

    signal = result["signals"][0]
    assert signal["direction"] == "LONG"
    assert signal["signal_id"]
    order = result["orders"][0]
    assert order["state"] == "FILLED"
    assert order["risk_decision"]["decision"] == "ALLOW"
    # OrderIntent idempotency key contract: f"{strategy_id}:{signal_id}"
    created = manager.store.order_journal(order["client_order_id"])[0]
    assert created["idempotency_key"] == (
        f"{signal['strategy_id']}:{signal['signal_id']}:created"
    )

    journal = assert_journal_legal(manager, order["client_order_id"])
    assert [leg["state"] for leg in journal] == [
        "CREATED",
        "PREPARED",
        "SUBMITTING",
        "SUBMITTED",
        "FILLED",
    ]

    positions = manager.exchange.fetch_positions("acct-run-chain")
    assert positions[0]["side"] == "LONG"
    assert positions[0]["quantity"] > 0

    marked = manager.refresh_market_data(["BTCUSDT"], force=True)
    assert marked["markedPositions"] == 1
    position = manager.exchange.fetch_positions("acct-run-chain")[0]
    assert position["mark_price"] == 61200
    assert position["unrealized_pnl"] > 0

    reconciliation = manager.command(
        "reconcile", "reconcile-chain-1", {"account_id": "acct-run-chain"}
    )
    assert reconciliation["status"] == "RECONCILED"
    assert reconciliation["drift"]["local_fills"] == 1
    assert reconciliation["opening_paused"] is False

    run = manager.store.get_run("run-chain")
    assert run["performance"]["orders"] == 1
    assert_all_journals_legal(manager)


def test_signal_order_idempotency_dedup(tmp_path):
    manager = RuntimeManager(str(tmp_path / "dedup.sqlite3"))
    manager.market_data = SequentialMarketData([60000, 60600])
    activate(manager, "run-dedup", "PAPER")
    manager.refresh_market_data(["BTCUSDT"], force=True)
    result = manager.refresh_market_data(["BTCUSDT"], force=True)
    order = manager._paper_order(result["signals"][0])

    duplicate = manager.command("submit_order", "dup-command-1", order)
    triplicate = manager.command("submit_order", "dup-command-2", order)

    assert duplicate["idempotent"] is True
    assert triplicate["idempotent"] is True
    assert duplicate["client_order_id"] == result["orders"][0]["client_order_id"]
    journal = manager.store.order_journal(order["client_order_id"])
    assert [leg["state"] for leg in journal].count("FILLED") == 1


def test_kill_switch_blocks_mock_and_shadow_adapters(tmp_path):
    manager = RuntimeManager(str(tmp_path / "kill.sqlite3"))
    fake_binance = FakeBinanceAdapter()
    manager._gateways[("BINANCE", "testnet")] = fake_binance
    activate(manager, "run-kill", "PAPER")

    manager.command("kill_switch", "kill-on-1", {"enabled": True})
    rejected_mock = manager.command(
        "submit_order", "kill-order-1", base_order("run-kill", "acct-run-kill")
    )
    assert rejected_mock["state"] == "REJECTED"
    assert "GLOBAL_KILL_SWITCH" in rejected_mock["risk_decision"]["reasons"]

    shadow_order = base_order(
        "run-kill",
        "acct-run-kill",
        mode="SHADOW",
        venue="BINANCE",
        idempotency_key="kill-shadow-1",
        account={"venue": "BINANCE", "environment": "testnet"},
    )
    rejected_shadow = manager.command("submit_order", "kill-order-2", shadow_order)
    assert rejected_shadow["state"] == "REJECTED"
    assert "GLOBAL_KILL_SWITCH" in rejected_shadow["risk_decision"]["reasons"]
    assert fake_binance.book_calls == 0  # rejected before touching the adapter

    manager.command("kill_switch", "kill-off-1", {"enabled": False})
    accepted = manager.command(
        "submit_order",
        "kill-order-3",
        base_order("run-kill", "acct-run-kill", idempotency_key="kill-after-1"),
    )
    assert accepted["state"] == "ACCEPTED"


def test_pause_blocks_new_intents_resume_allows(tmp_path):
    manager = RuntimeManager(str(tmp_path / "pause.sqlite3"))
    activate(manager, "run-pause", "PAPER")

    paused = manager.command("pause", "pause-1", {"run_id": "run-pause"})
    assert paused["status"] == "PAUSED"
    rejected = manager.command(
        "submit_order", "paused-order-1", base_order("run-pause", "acct-run-pause")
    )
    assert rejected["state"] == "REJECTED"
    assert "RUN_PAUSED" in rejected["risk_decision"]["reasons"]

    # Reduce-only closes remain allowed while paused.
    reduce_only = manager.command(
        "submit_order",
        "paused-order-2",
        base_order(
            "run-pause", "acct-run-pause", reduce_only=True, idempotency_key="ro-1"
        ),
    )
    assert reduce_only["state"] == "ACCEPTED"

    resumed = manager.command("resume", "resume-1", {"run_id": "run-pause"})
    assert resumed["status"] == "RUNNING"
    accepted = manager.command(
        "submit_order",
        "paused-order-3",
        base_order("run-pause", "acct-run-pause", idempotency_key="after-resume-1"),
    )
    assert accepted["state"] == "ACCEPTED"


def test_stop_cancels_open_orders_before_stopping(tmp_path):
    manager = RuntimeManager(str(tmp_path / "stop.sqlite3"))
    activate(manager, "run-stop", "PAPER")
    resting = manager.command(
        "submit_order",
        "stop-order-1",
        base_order(
            "run-stop",
            "acct-run-stop",
            fill_immediately=False,
            idempotency_key="resting-1",
        ),
    )
    assert resting["state"] == "ACCEPTED"

    stopped = manager.command("stop", "stop-1", {"run_id": "run-stop"})

    assert stopped["status"] == "STOPPED"
    assert len(stopped["canceled_orders"]) == 1
    assert stopped["canceled_orders"][0]["state"] == "CANCELED"
    assert (
        manager.store.latest_order(resting["client_order_id"])["state"] == "CANCELED"
    )
    assert_journal_legal(manager, resting["client_order_id"])


def test_restart_recovery_between_fill_and_reconcile(tmp_path):
    path = str(tmp_path / "restart.sqlite3")
    manager = RuntimeManager(path)
    manager.market_data = SequentialMarketData([60000, 60600])
    activate(manager, "run-restart", "PAPER")
    manager.refresh_market_data(["BTCUSDT"], force=True)
    result = manager.refresh_market_data(["BTCUSDT"], force=True)
    assert result["orders"][0]["state"] == "FILLED"
    # Simulate a process kill right after an order entered SUBMITTING.
    manager.store.append_order(
        {
            "client_order_id": "uncertain-1",
            "sequence": 1,
            "idempotency_key": "uncertain-1:created",
            "run_id": "run-restart",
            "account_id": "acct-run-restart",
            "state": "SUBMITTING",
            "quantity": 0.01,
            "remaining_quantity": 0.01,
        }
    )
    del manager  # process kill: in-memory gateway state is lost

    restarted = RuntimeManager(path)

    assert restarted.recovered_orders == 1
    uncertain = restarted.store.latest_order("uncertain-1")
    assert uncertain["state"] == "RECONCILIATION_REQUIRED"
    # Mock adapter has no independent record of the uncertain order: fail
    # closed by pausing opening for the account.
    assert "acct-run-restart" in restarted.risk.pause_opening_accounts
    assert restarted.recovery_report["unresolved"] == 1
    # The filled order's journal survived the restart unclobbered and legal.
    assert_all_journals_legal(restarted)
    # Positions and fills were persisted and reload cleanly.
    positions = restarted.exchange.fetch_positions("acct-run-restart")
    assert positions[0]["side"] == "LONG"
    blocked = restarted.command(
        "submit_order",
        "post-restart-1",
        base_order("run-restart", "acct-run-restart", idempotency_key="post-1"),
    )
    assert blocked["state"] == "REJECTED"
    assert "OPENING_PAUSED" in blocked["risk_decision"]["reasons"]


def test_restart_recovery_resolves_adapter_known_order(tmp_path):
    path = str(tmp_path / "restart-known.sqlite3")
    first = RuntimeManager(path)
    # An order whose last journal leg was SUBMITTED when the process died.
    first.store.append_order(
        {
            "client_order_id": "known-1",
            "sequence": 1,
            "idempotency_key": "known-1:created",
            "run_id": "run-known",
            "account_id": "acct-known",
            "state": "SUBMITTED",
            "quantity": 0.01,
            "remaining_quantity": 0.01,
            "instrument": "BTCUSDT",
        }
    )
    del first

    restarted = RuntimeManager(path)
    assert restarted.store.latest_order("known-1")["state"] == "RECONCILIATION_REQUIRED"
    assert restarted.recovery_report["unresolved"] == 1

    # The account's adapter knows the real remote state; recovery journals a
    # legal transition out of RECONCILIATION_REQUIRED.
    class AdapterGateway:
        def fetch_order(self, client_order_id):
            return {
                "state": "ACCEPTED",
                "exchange_order_id": "ex-1",
                "filled_quantity": 0.0,
            }

    restarted._gateways[("MOCKX", "paper")] = AdapterGateway()
    restarted.store.upsert_run(
        {
            "id": "run-known",
            "strategy_id": "strategy-known",
            "strategy_version": 1,
            "account_id": "acct-known",
            "account": {"venue": "MOCKX", "environment": "paper"},
            "mode": "PAPER",
            "status": "RUNNING",
            "strategy": {},
            "risk_policy": {},
            "performance": {},
            "market_history": {},
            "last_signal": {},
        }
    )
    report = restarted.recover()

    assert report["resolved"] == 1
    recovered = restarted.store.latest_order("known-1")
    assert recovered["state"] == "ACCEPTED"
    assert recovered["exchange_order_id"] == "ex-1"
    assert_journal_legal(restarted, "known-1")


# ------------------------------------------------------------ shadow mode


def test_shadow_simulated_fills_from_adapter_order_book(tmp_path):
    manager = RuntimeManager(str(tmp_path / "shadow.sqlite3"))
    fake_binance = FakeBinanceAdapter()
    manager._gateways[("BINANCE", "testnet")] = fake_binance
    manager.market_data = SequentialMarketData([60000, 60600, 59000])
    activate(
        manager,
        "run-shadow",
        "SHADOW",
        account={"venue": "BINANCE", "environment": "testnet"},
    )

    manager.refresh_market_data(["BTCUSDT"], force=True)
    result = manager.refresh_market_data(["BTCUSDT"], force=True)

    assert result["signals"][0]["direction"] == "LONG"
    order = result["orders"][0]
    assert order["state"] == "FILLED"
    assert order["shadow"] is True
    assert order["exchange_order_id"].startswith("shadow-")
    # Fill is priced from the adapter order book (VWAP walking ask depth), not
    # from the signal quote.
    quantity = order["filled_quantity"]
    remaining, cost = quantity, 0.0
    for price, size in fake_binance.book["asks"]:
        take = min(remaining, size)
        cost += take * price
        remaining -= take
        if remaining <= 0:
            break
    assert order["average_price"] == pytest.approx(cost / quantity)
    assert order["average_price"] == pytest.approx(60500.0)
    assert order["average_price"] != result["signals"][0]["price"]
    assert fake_binance.submit_calls == 0
    assert fake_binance.book_calls == 1

    shadow_gateway = manager.shadow_gateway_for_account(
        {"venue": "BINANCE", "environment": "testnet"}
    )
    positions = shadow_gateway.fetch_positions("acct-run-shadow")
    assert positions[0]["side"] == "LONG"
    assert positions[0]["mode"] == "SHADOW"
    assert_journal_legal(manager, order["client_order_id"])

    state = manager.account_state("acct-run-shadow")
    assert state["positions"][0]["side"] == "LONG"

    # Thin bids: the counter-signal rests without filling (no depth to walk).
    fake_binance.book = {"symbol": "BTCUSDT", "bids": [[58900.0, 0.0001]], "asks": []}
    thin = manager.refresh_market_data(["BTCUSDT"], force=True)
    assert thin["signals"][0]["direction"] == "SHORT"
    resting = thin["orders"][0]
    assert resting["state"] == "ACCEPTED"
    assert resting["filled_quantity"] == 0.0

    reconciliation = manager.command(
        "reconcile", "reconcile-shadow-1", {"account_id": "acct-run-shadow"}
    )
    assert reconciliation["status"] in {"RECONCILED", "RECONCILIATION_REQUIRED"}
    assert "drift" in reconciliation


# --------------------------------------------------- API control-plane E2E


class InProcessRuntime:
    """NautilusRuntimeClient-compatible client hitting the real runtime app."""

    def __init__(self):
        self.client = TestClient(runtime_main.app)

    def command(self, command_type, idempotency_key, payload):
        response = self.client.post(
            f"/commands/{command_type}",
            json={"idempotency_key": idempotency_key, "payload": payload},
            headers={"X-PG-Runtime-Secret": "dev-runtime-secret"},
        )
        if response.status_code >= 400:
            from packages.trading.runtime_client import RuntimeUnavailable

            raise RuntimeUnavailable(f"runtime HTTP {response.status_code}")
        return response.json()


def trading_account(db, user, *, venue="MOCK", account_type="PAPER", name="Paper"):
    row = TradingAccount(
        user_id=user.id,
        name=name,
        venue=venue,
        account_type=account_type,
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


def chain_draft():
    return {
        "name": "BTC chain strategy",
        "description": "P0-10a chain",
        "instruments": ["BTCUSDT"],
        "venues": ["MOCK"],
        "timeframe": "1h",
        "strategy_type": "trend",
        "entry_rules": [{"type": "momentum", "threshold": 0.001}],
        "exit_rules": [{"type": "stop"}],
        "sentiment_sources": ["rss"],
        "execution_mode": "PAPER",
        "max_notional": 1000,
        "max_position": 1,
    }


def test_backtest_paper_shadow_chain_via_api(
    api_client, db, max_user, tmp_path, monkeypatch
):
    manager = RuntimeManager(str(tmp_path / "api-chain.sqlite3"))
    runtime_main.manager = manager
    in_process = InProcessRuntime()
    monkeypatch.setattr(
        "apps.api.services.strategy_control_service.NautilusRuntimeClient",
        lambda *args, **kwargs: in_process,
    )
    fake_binance = FakeBinanceAdapter()

    paper = trading_account(db, max_user)
    binance = trading_account(
        db, max_user, venue="BINANCE", account_type="TESTNET", name="Testnet"
    )

    created = api_client.post(
        "/strategies",
        json={"draft": chain_draft()},
        headers={**auth_headers(max_user), "Idempotency-Key": "chain-create-1"},
    )
    assert created.status_code == 200
    strategy_id = created.json()["strategy"]["id"]
    assert created.json()["strategy"]["status"] == "DRAFT"

    # Backtest (P0-9 output) links the DRAFT to a versioned spec.
    backtest = run_strategy_backtest(db, max_user.id, strategy_id)
    assert backtest.strategy_id == strategy_id

    # ---- PAPER activation through the approval flow.
    preview = api_client.post(
        f"/strategies/{strategy_id}/paper",
        json={"account_id": paper.id},
        headers={**auth_headers(max_user), "Idempotency-Key": "chain-paper-1"},
    )
    assert preview.status_code == 200
    intent = preview.json()["intent"]
    assert intent["intent_type"] == "START_PAPER_STRATEGY"

    activation = api_client.post(
        f"/strategies/{strategy_id}/activate",
        json={"intent_id": intent["id"], "confirmation": intent["confirmation"]},
        headers=auth_headers(max_user),
    )
    assert activation.status_code == 200
    assert activation.json()["activation"]["status"] == "RUNNING"
    paper_run_id = activation.json()["run"]["runtime_run_id"]
    runtime_run = manager.store.get_run(paper_run_id)
    assert runtime_run["status"] == "RUNNING"
    assert runtime_run["account"]["venue"] == "MOCK"

    # Duplicate activation of the same intent is idempotent (rejected as a
    # no-op replay returning the original activation, no second run).
    duplicate = api_client.post(
        f"/strategies/{strategy_id}/activate",
        json={"intent_id": intent["id"], "confirmation": intent["confirmation"]},
        headers=auth_headers(max_user),
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["activation"]["id"] == activation.json()["activation"]["id"]
    assert len(manager.store.list_runs()) == 1

    # Drive the mock-adapter chain: signal -> journal -> position.
    manager.market_data = SequentialMarketData([60000, 60600])
    manager.refresh_market_data(["BTCUSDT"], force=True)
    paper_result = manager.refresh_market_data(["BTCUSDT"], force=True)
    assert paper_result["orders"][0]["state"] == "FILLED"
    paper_positions = manager.account_state(paper.id)["positions"]
    assert paper_positions[0]["side"] == "LONG"

    # ---- SHADOW activation of the same version against the testnet account.
    shadow_preview = api_client.post(
        f"/strategies/{strategy_id}/shadow",
        json={"account_id": binance.id},
        headers={**auth_headers(max_user), "Idempotency-Key": "chain-shadow-1"},
    )
    assert shadow_preview.status_code == 200
    shadow_intent = shadow_preview.json()["intent"]
    assert shadow_intent["intent_type"] == "START_SHADOW_STRATEGY"

    shadow_activation = api_client.post(
        f"/strategies/{strategy_id}/activate",
        json={
            "intent_id": shadow_intent["id"],
            "confirmation": shadow_intent["confirmation"],
        },
        headers=auth_headers(max_user),
    )
    assert shadow_activation.status_code == 200
    shadow_run_id = shadow_activation.json()["run"]["runtime_run_id"]
    runtime_shadow = manager.store.get_run(shadow_run_id)
    assert runtime_shadow["mode"] == "SHADOW"
    assert runtime_shadow["account"] == {"venue": "BINANCE", "environment": "testnet"}

    # Same chain with adapter prices: simulated fill from recorded book depth.
    manager._gateways[("BINANCE", "testnet")] = fake_binance
    manager.market_data = SequentialMarketData([60600, 61200])
    manager.refresh_market_data(["BTCUSDT"], force=True)
    shadow_result = manager.refresh_market_data(["BTCUSDT"], force=True)
    shadow_orders = [
        order
        for order in shadow_result["orders"]
        if order.get("run_id") == shadow_run_id
    ]
    assert shadow_orders[0]["state"] == "FILLED"
    assert shadow_orders[0]["shadow"] is True
    assert fake_binance.book_calls > 0
    assert fake_binance.submit_calls == 0
    shadow_positions = manager.account_state(binance.id)["positions"]
    assert shadow_positions[0]["side"] == "LONG"
    assert shadow_positions[0]["mode"] == "SHADOW"

    # ---- Pause/resume/stop round-trips (front/back consistency).
    paused = api_client.post(
        f"/strategies/{strategy_id}/pause", headers=auth_headers(max_user)
    )
    assert paused.status_code == 200
    assert paused.json()["run"]["status"] == "PAUSED"
    assert manager.store.get_run(shadow_run_id)["status"] == "PAUSED"
    strategy_view = api_client.get(
        f"/strategies/{strategy_id}", headers=auth_headers(max_user)
    )
    assert strategy_view.json()["strategy"]["latest_run"]["status"] == "PAUSED"
    blocked = manager.command(
        "submit_order",
        "api-paused-1",
        base_order(
            shadow_run_id,
            binance.id,
            mode="SHADOW",
            venue="BINANCE",
            idempotency_key="api-blocked-1",
        ),
    )
    assert "RUN_PAUSED" in blocked["risk_decision"]["reasons"]

    resumed = api_client.post(
        f"/strategies/{strategy_id}/resume", headers=auth_headers(max_user)
    )
    assert resumed.json()["run"]["status"] == "RUNNING"
    assert manager.store.get_run(shadow_run_id)["status"] == "RUNNING"

    stopped = api_client.post(
        f"/strategies/{strategy_id}/stop", headers=auth_headers(max_user)
    )
    assert stopped.json()["run"]["status"] == "STOPPED"
    assert manager.store.get_run(shadow_run_id)["status"] == "STOPPED"

    db_run = (
        db.query(StrategyRun).filter_by(runtime_run_id=shadow_run_id).one_or_none()
    )
    assert db_run.status == "STOPPED"
