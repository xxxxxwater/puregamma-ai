from __future__ import annotations

import hashlib
import uuid

from adapters.coinbase_advanced import CoinbaseAdvancedAdapter
from adapters.hyperliquid import HyperliquidAdapter
from adapters.shadow import ShadowExecutionAdapter
from app.adapter_registry import adapter_for, adapter_key
from app.event_bus import RuntimeEventBus
from app.exchange_gateway import MockExchangeGateway
from app.execution_gateway import RuntimeExecutionGateway, apply_transition
from app.config import get_settings
from app.market_data import (
    CoinbasePublicMarketProvider,
    HyperliquidPublicMarketProvider,
    PublicMarketDataRouter,
    normalize_asset,
)
from app.reconciliation import RuntimeReconciler
from app.nautilus_bridge import NautilusCoreBridge
from app.risk_gateway import RuntimeRiskGateway
from app.state_store import RuntimeStateStore
from app.strategy_runner import RuntimeStrategyRunner

TERMINAL_STATES = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}


def deterministic_client_order_id(strategy_id: str, signal_id: str) -> str:
    digest = hashlib.sha1(f"{strategy_id}:{signal_id}".encode()).hexdigest()[:20]
    return f"pg-{digest}"


class RuntimeManager:
    def __init__(self, state_db: str):
        settings = get_settings()
        self.settings = settings
        self.store = RuntimeStateStore(state_db)
        # Mark uncertain orders BEFORE gateways load persisted state so a
        # restarted mock gateway mirrors the post-recovery store truth.
        self.recovered_orders = self.store.recover_uncertain_orders()
        self.nautilus = NautilusCoreBridge()
        self.events = RuntimeEventBus(self.nautilus)
        self.exchange = MockExchangeGateway(self.store)
        self.external_adapters = [HyperliquidAdapter(), CoinbaseAdvancedAdapter()]
        self.risk = RuntimeRiskGateway()
        self.execution = RuntimeExecutionGateway(self.store, self.exchange, self.risk)
        self.runner = RuntimeStrategyRunner(self.store, self.events)
        self.reconciler = RuntimeReconciler(self.store, self.exchange, self.risk)
        # (venue, environment) -> exchange gateway for non-MOCK accounts.
        self._gateways: dict[tuple[str, str], object] = {}
        # (venue, environment) -> execution gateway bound to a live adapter.
        self._execution_gateways: dict[tuple[str, str], RuntimeExecutionGateway] = {}
        # (venue, environment) -> execution gateway bound to a shadow adapter.
        self._shadow_execution: dict[tuple[str, str], RuntimeExecutionGateway] = {}
        self._shadow_gateway_cache: dict[tuple[str, str], ShadowExecutionAdapter] = {}
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
        self.recovery_report = self.recover()

    # ------------------------------------------------------------ adapters

    def gateway_for_account(self, account: dict | None):
        """Resolve (and cache) the exchange gateway for an account record."""
        key = adapter_key(account)
        if key[0] == "MOCK":
            return self.exchange
        if key not in self._gateways:
            self._gateways[key] = adapter_for(account, config=self.settings, store=self.store)
        return self._gateways[key]

    def shadow_gateway_for_account(self, account: dict | None):
        """SHADOW gateway wrapping the account's real adapter (never submits)."""
        key = adapter_key(account)
        if key not in self._shadow_gateway_cache:
            real = self.gateway_for_account(account)
            self._shadow_gateway_cache[key] = ShadowExecutionAdapter(real, self.store)
        return self._shadow_gateway_cache[key]

    def shadow_execution_for_account(self, account: dict | None) -> RuntimeExecutionGateway:
        key = adapter_key(account)
        if key not in self._shadow_execution:
            self._shadow_execution[key] = RuntimeExecutionGateway(
                self.store, self.shadow_gateway_for_account(account), self.risk
            )
        return self._shadow_execution[key]

    def _account_config(self, account_id: str) -> dict:
        for run in self.store.list_runs():
            if run.get("account_id") == account_id and run.get("account"):
                return run["account"]
        return {"venue": "MOCK", "environment": "paper"}

    # -------------------------------------------------------------- health

    def health(self) -> dict:
        return {
            "status": "HEALTHY",
            "service": "nautilus-runtime",
            "adapter": self.exchange.health_check(),
            "adapters": [
                self.exchange.health_check(),
                *[adapter.health_check() for adapter in self.external_adapters],
                *[gateway.health_check() for gateway in self._gateways.values()],
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
            "recovery": self.recovery_report,
            "runs": len(self.store.list_runs()),
        }

    # ------------------------------------------------------------- recover

    def recover(self) -> dict:
        """Restart recovery: re-sync persisted orders/positions from adapters.

        Orders left in an uncertain state (SUBMITTING/SUBMITTED/CANCEL_PENDING)
        were already marked RECONCILIATION_REQUIRED by the store. Here each one
        is re-fetched from the account's adapter: a known remote state is
        journaled as a legal transition; an unknown remote state keeps the
        order RECONCILIATION_REQUIRED and pauses opening for that account.
        """
        report = {"resolved": 0, "unresolved": 0, "accounts_paused": []}
        for order in self.store.latest_orders():
            if order["state"] != "RECONCILIATION_REQUIRED":
                continue
            account = self._account_config(order["account_id"])
            gateway = self.gateway_for_account(account)
            remote = None
            try:
                remote = gateway.fetch_order(order["client_order_id"])
            except Exception:
                remote = None
            remote_state = (remote or {}).get("state")
            legal_targets = {"ACCEPTED", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED"}
            if remote_state in legal_targets:
                apply_transition(
                    self.store,
                    order,
                    remote_state,
                    exchange_order_id=remote.get("exchange_order_id"),
                    filled_quantity=float(remote.get("filled_quantity", 0)),
                    average_price=remote.get("average_price"),
                    idempotency_key=f"{order['client_order_id']}:recovered:{remote_state}",
                )
                report["resolved"] += 1
            else:
                self.risk.pause_opening_accounts.add(order["account_id"])
                self._pause_runs_for_account(
                    order["account_id"], "ORDER_RECONCILIATION_REQUIRED"
                )
                if order["account_id"] not in report["accounts_paused"]:
                    report["accounts_paused"].append(order["account_id"])
                report["unresolved"] += 1
        self.risk.sync_paused_runs(self.store.list_runs())
        return report

    # ------------------------------------------------------------ commands

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
                self.risk.sync_paused_runs(self.store.list_runs())
            elif command_type in {"pause", "resume", "stop"}:
                result = self._transition_run(payload["run_id"], command_type)
            elif command_type == "submit_order":
                result = self._submit_order(payload)
            elif command_type == "cancel_order":
                result = self.execution.cancel(
                    payload["account_id"], payload["client_order_id"], idempotency_key
                )
            elif command_type == "reconcile":
                result = self._reconcile(payload["account_id"])
            elif command_type == "kill_switch":
                result = self.risk.kill_switch(bool(payload["enabled"]))
            elif command_type == "refresh_market_data":
                result = self.refresh_market_data(
                    payload.get("symbols", []), force=True
                )
            else:
                raise ValueError("Unsupported runtime command")
            self.store.complete_command(command_id, "ACKNOWLEDGED", result)
            return {
                **result,
                "command_id": command_id,
                # Preserve inner idempotency (e.g. order-level dedup); the
                # command-replay path above already returned idempotent=True.
                "idempotent": bool(result.get("idempotent", False)),
            }
        except Exception as exc:
            result = {"status": "REJECTED", "error": str(exc)[:300]}
            self.store.complete_command(command_id, "REJECTED", result)
            return {**result, "command_id": command_id, "idempotent": False}

    def _transition_run(self, run_id: str, action: str) -> dict:
        run = self.store.get_run(run_id)
        if not run:
            raise LookupError("Runtime run not found")
        canceled = []
        if action == "stop":
            # Cancel resting orders first (reduce-only semantics: positions are
            # left untouched and may only be closed by reduce-only orders).
            execution = self._execution_for_run(run)
            for order in self.store.latest_orders(run.get("account_id")):
                if order.get("run_id") != run_id:
                    continue
                if order["state"] not in {"SUBMITTED", "ACCEPTED", "PARTIALLY_FILLED"}:
                    continue
                canceled.append(
                    execution.cancel(
                        order["account_id"],
                        order["client_order_id"],
                        f"stop:{run_id}:{order['client_order_id']}",
                    )
                )
        result = self.runner.transition(run_id, action)
        self.risk.sync_paused_runs(self.store.list_runs())
        if canceled:
            result = {**result, "canceled_orders": canceled}
        return result

    def _execution_for_run(self, run: dict) -> RuntimeExecutionGateway:
        account = run.get("account") or {}
        key = adapter_key(account)
        if key[0] == "MOCK":
            return self.execution
        if str(run.get("mode", "")).upper() == "SHADOW":
            return self.shadow_execution_for_account(account)
        if key not in self._execution_gateways:
            self._execution_gateways[key] = RuntimeExecutionGateway(
                self.store, self.gateway_for_account(account), self.risk
            )
        return self._execution_gateways[key]

    def _submit_order(self, payload: dict) -> dict:
        account = payload.get("account") or self._account_config(payload["account_id"])
        key = adapter_key(account)
        if key[0] == "MOCK":
            return self.execution.submit(payload)
        if str(payload.get("mode", "")).upper() == "SHADOW":
            return self.shadow_execution_for_account(account).submit(payload)
        if key not in self._execution_gateways:
            self._execution_gateways[key] = RuntimeExecutionGateway(
                self.store, self.gateway_for_account(account), self.risk
            )
        return self._execution_gateways[key].submit(payload)

    def _reconcile(self, account_id: str) -> dict:
        account = self._account_config(account_id)
        gateway = self.gateway_for_account(account)
        if str(self._run_mode(account_id)) == "SHADOW":
            # SHADOW reconciles the journal against simulated paper accounting.
            gateway = self.shadow_gateway_for_account(account)
        if gateway is self.exchange:
            result = self.reconciler.reconcile(account_id)
            if result.get("status") != "RECONCILED":
                self._pause_runs_for_account(account_id, "RECONCILIATION_REQUIRED")
            return result
        result = RuntimeReconciler(self.store, gateway, self.risk).reconcile(account_id)
        if result.get("status") != "RECONCILED":
            self._pause_runs_for_account(account_id, "RECONCILIATION_REQUIRED")
        self.store.event("RECONCILIATION", account_id, {
            "account_id": account_id,
            "status": result["status"],
            "unknown_orders": result["unknown_orders"],
            "venue": account.get("venue", "MOCK"),
        })
        return result

    # --------------------------------------------------------- market data

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
        self._pause_runs_for_missing_market_data(set(snapshot.get("missing", [])))
        marked_positions = self.exchange.mark_positions(snapshot["quotes"])
        for gateway in self._shadow_gateway_cache.values():
            marked_positions += gateway.mark_positions(snapshot["quotes"])
        signals = self.runner.evaluate_market(snapshot["quotes"])
        orders = []
        for signal in signals:
            run = self.store.get_run(signal["run_id"])
            if signal["mode"] == "PAPER":
                order = self._paper_order(signal)
                result = self.execution.submit(order)
            elif signal["mode"] == "SHADOW" and self._shadow_capable(run):
                order = self._shadow_order(signal, run)
                result = self.shadow_execution_for_account(run["account"]).submit(order)
            else:
                continue
            orders.append(result)
            self.store.event(f"{signal['mode']}_ORDER", signal["run_id"], result)
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

    @staticmethod
    def _shadow_capable(run: dict | None) -> bool:
        if not run:
            return False
        venue, _ = adapter_key(run.get("account"))
        return venue != "MOCK"

    def account_state(self, account_id: str) -> dict:
        account = self._account_config(account_id)
        gateway = self.gateway_for_account(account)
        if str(self._run_mode(account_id)) == "SHADOW":
            gateway = self.shadow_gateway_for_account(account)
        return {
            "account": gateway.fetch_account(account_id),
            "positions": gateway.fetch_positions(account_id),
            "orders": self.store.latest_orders(account_id),
            "open_orders": gateway.fetch_open_orders(account_id),
            "fills": gateway.fetch_fills(account_id),
        }

    def _run_mode(self, account_id: str) -> str | None:
        for run in self.store.list_runs():
            if run.get("account_id") == account_id:
                return run.get("mode")
        return None

    def _active_instruments(self) -> list[str]:
        instruments = []
        for run in self.store.list_runs():
            if run["status"] == "RUNNING":
                instruments.extend(run.get("strategy", {}).get("instruments", []))
        return list(
            dict.fromkeys(instruments or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "HYPEUSDT"])
        )

    def _pause_runs_for_missing_market_data(self, missing_assets: set[str]) -> None:
        if not missing_assets:
            return
        normalized_missing = {normalize_asset(asset) for asset in missing_assets}
        for run in self.store.list_runs():
            if run.get("status") != "RUNNING":
                continue
            instruments = run.get("strategy", {}).get("instruments", [])
            if not any(normalize_asset(item) in normalized_missing for item in instruments):
                continue
            account_id = run.get("account_id")
            if account_id:
                self.risk.pause_opening_accounts.add(account_id)
            self._pause_run(run, "MARKET_DATA_STALE")
        self.risk.sync_paused_runs(self.store.list_runs())

    def _pause_runs_for_account(self, account_id: str, reason: str) -> None:
        self.risk.pause_opening_accounts.add(account_id)
        for run in self.store.list_runs():
            if run.get("account_id") != account_id or run.get("status") != "RUNNING":
                continue
            self._pause_run(run, reason)
        self.risk.sync_paused_runs(self.store.list_runs())

    def _pause_run(self, run: dict, reason: str) -> None:
        run["status"] = "PAUSED"
        run["pause_reason"] = reason
        self.store.upsert_run(run)
        self.store.event("RUN_PAUSED", run["id"], run)
        self.events.publish("RUN_PAUSED", run)

    @staticmethod
    def _base_order(signal: dict, mode: str) -> dict:
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
        side = "BUY" if signal["direction"] == "LONG" else "SELL"
        return {
            "client_order_id": deterministic_client_order_id(
                signal["strategy_id"], signal["signal_id"]
            ),
            "account_id": signal["account_id"],
            "strategy_id": signal["strategy_id"],
            "run_id": signal["run_id"],
            "instrument": signal["instrument"],
            "direction": side,
            "side": side,
            "quantity": max(quantity, 0.000001),
            "notional": notional,
            "leverage": min(float(strategy.get("leverage", 1)), 5.0),
            "order_type": "MARKET",
            "reduce_only": False,
            "mode": mode,
            "risk_policy": policy,
            "idempotency_key": f"{signal['strategy_id']}:{signal['signal_id']}",
            "market_provider": signal["provider"],
            "source_timestamp": signal["source_timestamp"],
            "market_stale": bool(signal.get("market_stale", False)),
        }

    @classmethod
    def _paper_order(cls, signal: dict) -> dict:
        return {
            **cls._base_order(signal, "PAPER"),
            "venue": "MOCK",
            "fill_immediately": True,
            "mark_price": signal["price"],
        }

    @classmethod
    def _shadow_order(cls, signal: dict, run: dict | None = None) -> dict:
        venue, environment = adapter_key((run or {}).get("account"))
        return {
            **cls._base_order(signal, "SHADOW"),
            "venue": venue,
            "environment": environment,
            "account": (run or {}).get("account") or {},
        }
