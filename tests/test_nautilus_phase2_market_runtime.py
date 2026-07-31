from __future__ import annotations

import sys
from pathlib import Path

import httpx
from fastapi.testclient import TestClient


RUNTIME_ROOT = Path(__file__).parents[1] / "services" / "nautilus-runtime"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from app import main as runtime_main  # noqa: E402
from app.market_data import (  # noqa: E402
    HyperliquidPublicMarketProvider,
    PublicMarketDataRouter,
)
from app.runtime_manager import RuntimeManager  # noqa: E402


def response(status: int, payload) -> httpx.Response:
    return httpx.Response(
        status,
        json=payload,
        request=httpx.Request("POST", "https://api.hyperliquid.xyz/info"),
    )


def test_hyperliquid_public_all_mids_normalization(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: response(200, {"BTC": "60000.5", "ETH": "3200"}),
    )
    provider = HyperliquidPublicMarketProvider(
        "https://api.hyperliquid.xyz",
        timeout=1,
        failure_threshold=3,
        recovery_seconds=30,
    )

    quotes = provider.fetch_quotes(["BTC", "ETH", "SOL"])

    assert [quote["asset"] for quote in quotes] == ["BTC", "ETH"]
    assert quotes[0]["price"] == 60000.5
    assert quotes[0]["provider"] == "hyperliquid_public"
    assert provider.status()["status"] == "HEALTHY"
    assert provider.status()["liveOrders"] is False


def test_market_router_uses_cache_and_fallback():
    class Provider:
        def __init__(self, name, values):
            self.provider_name = name
            self.values = values
            self.calls = 0

        def fetch_quotes(self, assets):
            self.calls += 1
            return [self.values[asset] for asset in assets if asset in self.values]

        def status(self):
            return {"provider": self.provider_name, "status": "HEALTHY"}

    stamp = "2026-07-11T00:00:00+00:00"
    first = Provider(
        "first",
        {
            "BTC": {
                "asset": "BTC",
                "symbol": "BTCUSDT",
                "price": 60000,
                "provider": "first",
                "timestamp": stamp,
                "stale": False,
            }
        },
    )
    second = Provider(
        "second",
        {
            "SOL": {
                "asset": "SOL",
                "symbol": "SOLUSD",
                "price": 150,
                "provider": "second",
                "timestamp": stamp,
                "stale": False,
            }
        },
    )
    router = PublicMarketDataRouter([first, second], cache_ttl_seconds=30)

    initial = router.fetch(["BTCUSDT", "SOLUSDT"])
    cached = router.fetch(["BTCUSDT", "SOLUSDT"])

    assert {quote["asset"] for quote in initial["quotes"]} == {"BTC", "SOL"}
    assert initial["missing"] == []
    assert first.calls == 1 and second.calls == 1
    assert cached["quotes"] == initial["quotes"]
    assert first.calls == 1 and second.calls == 1


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
            "timestamp": f"2026-07-11T00:00:{int(price) % 60:02d}+00:00",
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


def activate(manager: RuntimeManager, run_id: str, mode: str):
    return manager.command(
        "activate",
        f"activation-{run_id}",
        {
            "run_id": run_id,
            "strategy_id": f"strategy-{run_id}",
            "strategy_version": 1,
            "account_id": "paper-account",
            "mode": mode,
            "strategy": {
                "name": "BTC public momentum",
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
                "max_orders_per_minute": 5,
            },
        },
    )


def test_public_quote_drives_paper_fill(tmp_path):
    manager = RuntimeManager(str(tmp_path / "paper.sqlite3"))
    manager.market_data = SequentialMarketData([60000, 60600])
    activate(manager, "paper-run", "PAPER")

    assert manager.refresh_market_data(["BTCUSDT"], force=True)["signals"] == []
    result = manager.refresh_market_data(["BTCUSDT"], force=True)

    assert result["signals"][0]["direction"] == "LONG"
    assert result["orders"][0]["state"] == "FILLED"
    assert manager.exchange.fetch_positions("paper-account")[0]["side"] == "LONG"
    assert (
        manager.store.list_events(event_type="STRATEGY_SIGNAL")[0]["payload"][
            "provider"
        ]
        == "test_public"
    )

    restarted = RuntimeManager(str(tmp_path / "paper.sqlite3"))
    position = restarted.exchange.fetch_positions("paper-account")[0]
    assert position["side"] == "LONG"
    assert restarted.store.latest_orders("paper-account")[0]["state"] == "FILLED"


def test_paper_position_mark_to_market_updates_equity(tmp_path):
    manager = RuntimeManager(str(tmp_path / "mark.sqlite3"))
    manager.market_data = SequentialMarketData([60000, 60600, 61200])
    activate(manager, "mark-run", "PAPER")

    manager.refresh_market_data(force=True)
    manager.refresh_market_data(force=True)
    result = manager.refresh_market_data(force=True)
    state = manager.account_state("paper-account")

    assert result["markedPositions"] == 1
    assert state["positions"][0]["mark_price"] == 61200
    assert state["positions"][0]["unrealized_pnl"] > 0
    assert state["account"]["equity"] > 100000


def test_shadow_quote_never_creates_order(tmp_path):
    manager = RuntimeManager(str(tmp_path / "shadow.sqlite3"))
    manager.market_data = SequentialMarketData([60000, 59000])
    activate(manager, "shadow-run", "SHADOW")

    manager.refresh_market_data(["BTCUSDT"], force=True)
    result = manager.refresh_market_data(["BTCUSDT"], force=True)

    assert result["signals"][0]["direction"] == "SHORT"
    assert result["orders"] == []
    assert manager.exchange.fetch_positions("paper-account") == []


def test_runtime_market_endpoint_requires_internal_auth(tmp_path):
    runtime_main.manager = RuntimeManager(str(tmp_path / "endpoint.sqlite3"))
    runtime_main.manager.market_data = SequentialMarketData([60000])
    client = TestClient(runtime_main.app)

    assert client.get("/market/quotes").status_code == 401
    allowed = client.get(
        "/market/quotes?symbols=BTCUSDT&refresh=true",
        headers={"X-PG-Runtime-Secret": "dev-runtime-secret"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["quotes"][0]["asset"] == "BTC"
    assert allowed.json()["liveOrders"] is False
    assert client.get("/accounts/paper-account/state").status_code == 401
    state = client.get("/accounts/paper-account/state", headers={"X-PG-Runtime-Secret": "dev-runtime-secret"})
    assert state.status_code == 200
    assert state.json()["account"]["account_id"] == "paper-account"
