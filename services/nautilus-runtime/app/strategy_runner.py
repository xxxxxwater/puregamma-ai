from __future__ import annotations

from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeStrategyRunner:
    def __init__(self, store, event_bus):
        self.store = store
        self.event_bus = event_bus

    def start(self, command: dict) -> dict:
        mode = command["mode"].upper()
        if mode not in {"PAPER", "SHADOW"}:
            raise ValueError("Only PAPER and SHADOW runs are supported")
        run = {
            "id": command["run_id"],
            "strategy_id": command["strategy_id"],
            "strategy_version": command["strategy_version"],
            "account_id": command.get("account_id"),
            "account": command.get("account") or {},
            "mode": mode,
            "status": "RUNNING",
            "strategy": command["strategy"],
            "risk_policy": command.get("risk_policy", {}),
            "started_at": now_iso(),
            "stopped_at": None,
            "performance": {"signals": 0, "orders": 0, "pnl": 0.0, "drawdown": 0.0},
            "market_history": {},
            "last_signal": {},
        }
        self.store.upsert_run(run)
        self.store.event("RUN_STARTED", run["id"], run)
        self.event_bus.publish("RUN_STARTED", run)
        return run

    def transition(self, run_id: str, action: str) -> dict:
        run = self.store.get_run(run_id)
        if not run:
            raise LookupError("Runtime run not found")
        transitions = {"pause": "PAUSED", "resume": "RUNNING", "stop": "STOPPED"}
        if action not in transitions:
            raise ValueError("Unsupported run action")
        if action == "resume" and run["status"] != "PAUSED":
            raise ValueError("Only paused runs can resume")
        if action == "pause" and run["status"] != "RUNNING":
            raise ValueError("Only running runs can pause")
        run["status"] = transitions[action]
        if action == "stop":
            run["stopped_at"] = now_iso()
        self.store.upsert_run(run)
        self.store.event(f"RUN_{run['status']}", run_id, run)
        self.event_bus.publish(f"RUN_{run['status']}", run)
        return run

    def evaluate_market(self, quotes: list[dict]) -> list[dict]:
        signals = []
        quote_by_asset = {quote["asset"]: quote for quote in quotes}
        for run in self.store.list_runs():
            if run["status"] != "RUNNING":
                continue
            instruments = run.get("strategy", {}).get("instruments", [])
            for instrument in instruments:
                asset = normalize_asset(instrument)
                quote = quote_by_asset.get(asset)
                if not quote:
                    continue
                history = run.setdefault("market_history", {}).setdefault(asset, [])
                history.append(
                    {"price": float(quote["price"]), "timestamp": quote["timestamp"]}
                )
                del history[:-20]
                if len(history) < 2:
                    self.store.upsert_run(run)
                    continue
                previous = float(history[-2]["price"])
                change = float(quote["price"]) / previous - 1 if previous else 0.0
                threshold = self._threshold(run["strategy"])
                direction = (
                    "LONG"
                    if change >= threshold
                    else "SHORT"
                    if change <= -threshold
                    else "HOLD"
                )
                prior_direction = run.setdefault("last_signal", {}).get(asset)
                if direction == "HOLD" or direction == prior_direction:
                    self.store.upsert_run(run)
                    continue
                signal = {
                    "signal_id": f"{run['id']}:{asset}:{direction}:{quote['timestamp']}",
                    "run_id": run["id"],
                    "strategy_id": run["strategy_id"],
                    "strategy_version": run["strategy_version"],
                    "account_id": run.get("account_id"),
                    "mode": run["mode"],
                    "asset": asset,
                    "instrument": instrument,
                    "direction": direction,
                    "price": float(quote["price"]),
                    "change": change,
                    "threshold": threshold,
                    "provider": quote["provider"],
                    "source_timestamp": quote["timestamp"],
                    "created_at": now_iso(),
                    "risk_policy": run.get("risk_policy", {}),
                    "strategy": run["strategy"],
                }
                run["last_signal"][asset] = direction
                run["performance"]["signals"] = (
                    int(run["performance"].get("signals", 0)) + 1
                )
                self.store.upsert_run(run)
                self.store.event("STRATEGY_SIGNAL", run["id"], signal)
                self.event_bus.publish("STRATEGY_SIGNAL", signal)
                signals.append(signal)
        return signals

    @staticmethod
    def _threshold(strategy: dict) -> float:
        rules = strategy.get("entry_rules") or []
        if rules and isinstance(rules[0], dict):
            value = rules[0].get("threshold") or rules[0].get("minimum_change")
            if value is not None:
                return max(0.0001, min(abs(float(value)), 0.2))
        return 0.002


def normalize_asset(value: str) -> str:
    symbol = value.upper().split(".", 1)[0].replace("-PERP", "")
    for quote in ("USDT", "USDC", "USD"):
        if symbol.endswith(quote):
            return symbol[: -len(quote)]
    return symbol
