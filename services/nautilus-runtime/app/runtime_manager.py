from __future__ import annotations

import uuid

from adapters.coinbase_advanced import CoinbaseAdvancedAdapter
from adapters.hyperliquid import HyperliquidAdapter
from app.event_bus import RuntimeEventBus
from app.exchange_gateway import MockExchangeGateway
from app.execution_gateway import RuntimeExecutionGateway
from app.config import get_settings
from app.market_data import (
    CoinbasePublicMarketProvider,
    HyperliquidPublicMarketProvider,
    PublicMarketDataRouter,
)
from app.reconciliation import RuntimeReconciler
from app.nautilus_bridge import NautilusCoreBridge
from app.risk_gateway import RuntimeRiskGateway
from app.state_store import RuntimeStateStore
from app.strategy_runner import RuntimeStrategyRunner


class RuntimeManager:
    def __init__(self, state_db: str):
        settings = get_settings()
        self.store = RuntimeStateStore(state_db)
        self.nautilus = NautilusCoreBridge()
        self.events = RuntimeEventBus(self.nautilus)
        self.exchange = MockExchangeGateway(self.store)
        self.external_adapters = [HyperliquidAdapter(), CoinbaseAdvancedAdapter()]
        self.risk = RuntimeRiskGateway()
        self.execution = RuntimeExecutionGateway(self.store, self.exchange, self.risk)
        self.runner = RuntimeStrategyRunner(self.store, self.events)
        self.reconciler = RuntimeReconciler(self.store, self.exchange, self.risk)
        provider_args = {
            "timeout": settings.market_data_timeout_seconds,
            "failure_threshold": settings.market_data_failure_threshold,
            "recovery_seconds": settings.market_data_recovery_seconds,
        }
        self.market_data_enabled = settings.public_market_data_enabled
        self.market_data = PublicMarketDataRouter(
            [
                HyperliquidPublicMarketProvider(
                    settings.hyperliquid_public_url, **provider_args
                ),
                CoinbasePublicMarketProvider(
                    settings.coinbase_public_url, **provider_args
                ),
            ],
            cache_ttl_seconds=settings.market_data_cache_ttl_seconds,
        )
        self.recovered_orders = self.store.recover_uncertain_orders()

    def health(self) -> dict:
        return {
            "status": "HEALTHY",
            "service": "nautilus-runtime",
            "adapter": self.exchange.health_check(),
            "adapters": [
                self.exchange.health_check(),
                *[adapter.health_check() for adapter in self.external_adapters],
            ],
            "marketData": {
                "enabled": self.market_data_enabled,
                "providers": self.market_data.status(),
                "quotes": len(self.store.list_market_quotes()),
            },
            "nautilus": self.nautilus.status(),
            "nautilusInstalled": self.nautilus.available,
            "modes": ["BACKTEST", "PAPER", "SHADOW"],
            "liveTrading": False,
            "withdrawal": False,
            "transfer": False,
            "killSwitch": self.risk.global_kill_switch,
            "recoveredOrders": self.recovered_orders,
            "runs": len(self.store.list_runs()),
        }

    def command(self, command_type: str, idempotency_key: str, payload: dict) -> dict:
        command_id = f"cmd-{uuid.uuid4()}"
        command, created = self.store.command(
            command_id, idempotency_key, command_type, payload
        )
        if not created:
            return {
                **command["result"],
                "command_id": command["id"],
                "idempotent": True,
            }
        try:
            if command_type == "activate":
                result = self.runner.start(payload)
            elif command_type in {"pause", "resume", "stop"}:
                result = self.runner.transition(payload["run_id"], command_type)
            elif command_type == "submit_order":
                result = self.execution.submit(payload)
            elif command_type == "cancel_order":
                result = self.execution.cancel(
                    payload["account_id"], payload["client_order_id"], idempotency_key
                )
            elif command_type == "reconcile":
                result = self.reconciler.reconcile(payload["account_id"])
            elif command_type == "kill_switch":
                result = self.risk.kill_switch(bool(payload["enabled"]))
            elif command_type == "refresh_market_data":
                result = self.refresh_market_data(
                    payload.get("symbols", []), force=True
                )
            else:
                raise ValueError("Unsupported runtime command")
            self.store.complete_command(command_id, "ACKNOWLEDGED", result)
            return {**result, "command_id": command_id, "idempotent": False}
        except Exception as exc:
            result = {"status": "REJECTED", "error": str(exc)[:300]}
            self.store.complete_command(command_id, "REJECTED", result)
            return {**result, "command_id": command_id, "idempotent": False}

    def refresh_market_data(
        self, symbols: list[str] | None = None, *, force: bool = False
    ) -> dict:
        if not self.market_data_enabled:
            return {
                "status": "DISABLED",
                "quotes": self.store.list_market_quotes(),
                "signals": [],
                "orders": [],
                "liveOrders": False,
            }
        requested = symbols or self._active_instruments()
        snapshot = self.market_data.fetch(requested, force=force)
        self.store.save_market_quotes(snapshot["quotes"])
        marked_positions = self.exchange.mark_positions(snapshot["quotes"])
        signals = self.runner.evaluate_market(snapshot["quotes"])
        orders = []
        for signal in signals:
            if signal["mode"] != "PAPER":
                continue
            order = self._paper_order(signal)
            result = self.execution.submit(order)
            orders.append(result)
            self.store.event("PAPER_ORDER", signal["run_id"], result)
            run = self.store.get_run(signal["run_id"])
            if run:
                run["performance"]["orders"] = (
                    int(run["performance"].get("orders", 0)) + 1
                )
                self.store.upsert_run(run)
        return {
            **snapshot,
            "status": "HEALTHY" if snapshot["quotes"] else "DEGRADED",
            "signals": signals,
            "orders": orders,
            "markedPositions": marked_positions,
            "persistedQuotes": self.store.list_market_quotes(),
        }

    def account_state(self, account_id: str) -> dict:
        return {
            "account": self.exchange.fetch_account(account_id),
            "positions": self.exchange.fetch_positions(account_id),
            "orders": self.store.latest_orders(account_id),
            "open_orders": self.exchange.fetch_open_orders(account_id),
            "fills": self.exchange.fetch_fills(account_id),
        }

    def _active_instruments(self) -> list[str]:
        instruments = []
        for run in self.store.list_runs():
            if run["status"] == "RUNNING":
                instruments.extend(run.get("strategy", {}).get("instruments", []))
        return list(
            dict.fromkeys(instruments or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "HYPEUSDT"])
        )

    @staticmethod
    def _paper_order(signal: dict) -> dict:
        strategy = signal["strategy"]
        policy = signal.get("risk_policy", {})
        max_notional = min(
            float(strategy.get("max_notional", 10_000)),
            float(policy.get("max_notional", 10_000)),
        )
        max_position = min(
            float(strategy.get("max_position", 1)), float(policy.get("max_position", 1))
        )
        notional = max(1.0, min(max_notional, max_notional * 0.1))
        quantity = min(max_position, notional / float(signal["price"]))
        bucket = signal["source_timestamp"][:16]
        return {
            "account_id": signal["account_id"],
            "strategy_id": signal["strategy_id"],
            "run_id": signal["run_id"],
            "instrument": signal["instrument"],
            "venue": "MOCK",
            "direction": "BUY" if signal["direction"] == "LONG" else "SELL",
            "side": "BUY" if signal["direction"] == "LONG" else "SELL",
            "quantity": max(quantity, 0.000001),
            "notional": notional,
            "leverage": min(float(strategy.get("leverage", 1)), 5.0),
            "order_type": "MARKET",
            "reduce_only": False,
            "mode": "PAPER",
            "risk_policy": policy,
            "idempotency_key": f"paper:{signal['run_id']}:{signal['asset']}:{signal['direction']}:{bucket}",
            "fill_immediately": True,
            "mark_price": signal["price"],
            "market_provider": signal["provider"],
            "source_timestamp": signal["source_timestamp"],
        }
