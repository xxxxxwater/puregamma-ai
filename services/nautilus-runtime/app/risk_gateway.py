from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone


class RuntimeRiskGateway:
    def __init__(self, store=None):
        self.store = store
        self.global_kill_switch = False
        self.pause_opening_accounts: set[str] = set()
        self.paused_run_ids: set[str] = set()
        self._order_times: dict[str, deque[datetime]] = defaultdict(deque)

    def evaluate(self, order: dict, policy: dict, account: dict) -> dict:
        reasons: list[str] = []
        if self.global_kill_switch:
            reasons.append("GLOBAL_KILL_SWITCH")
        if order["account_id"] in self.pause_opening_accounts and not order.get(
            "reduce_only"
        ):
            reasons.append("OPENING_PAUSED")
        if order.get("run_id") in self.paused_run_ids and not order.get("reduce_only"):
            reasons.append("RUN_PAUSED")
        if order.get("mode") not in {"PAPER", "SHADOW"}:
            reasons.append("LIVE_EXECUTION_DISABLED")
        if float(order.get("notional", 0)) > float(policy.get("max_notional", 10_000)):
            reasons.append("MAX_NOTIONAL")
        if float(order.get("quantity", 0)) > float(policy.get("max_position", 1)):
            reasons.append("MAX_POSITION")
        if float(order.get("leverage", 1)) > min(
            5.0, float(policy.get("max_leverage", 1))
        ):
            reasons.append("MAX_LEVERAGE")
        if account.get("stale"):
            reasons.append("STALE_ACCOUNT")
        if float(account.get("daily_pnl", 0)) <= -abs(
            float(policy.get("max_daily_loss", 500))
        ):
            reasons.append("MAX_DAILY_LOSS")
        if float(account.get("drawdown", 0)) >= float(policy.get("max_drawdown", 0.1)):
            reasons.append("MAX_DRAWDOWN")

        # Aggregate exposure checks (integration task §5.4): limits apply to
        # the account's cumulative notional, and exposure must fit the
        # available margin — not just this single order.
        aggregate = self._aggregate_exposure(order, policy, account)
        if aggregate["reasons"]:
            reasons.extend(aggregate["reasons"])

        now = datetime.now(timezone.utc)
        queue = self._order_times[order["account_id"]]
        while queue and queue[0] < now - timedelta(minutes=1):
            queue.popleft()
        if len(queue) >= int(policy.get("max_orders_per_minute", 5)):
            reasons.append("ORDER_RATE_LIMIT")
        if not reasons:
            queue.append(now)
        return {
            "decision": "REJECT" if reasons else "ALLOW",
            "reasons": reasons,
            "limits": policy,
            "state": {
                "kill_switch": self.global_kill_switch,
                "opening_paused": order["account_id"] in self.pause_opening_accounts,
                "run_paused": order.get("run_id") in self.paused_run_ids,
                "aggregate": aggregate,
            },
        }

    def _aggregate_exposure(
        self, order: dict, policy: dict, account: dict
    ) -> dict:
        """Aggregate notional across every open paper position of the account.

        Enforces cumulative limits and an exposure-vs-margin check. Fails
        closed when a margin figure is unavailable but exposure is material.
        """
        reasons: list[str] = []
        position_notional = 0.0
        if self.store is not None:
            for position in self.store.list_paper_positions(order["account_id"]):
                position_notional += float(position.get("quantity", 0)) * float(
                    position.get("mark_price", position.get("average_price", 0)) or 0
                )
        order_notional = float(order.get("notional", 0))
        aggregate_after = position_notional + order_notional
        max_aggregate = float(policy.get("max_aggregate_notional", 0))
        if max_aggregate > 0 and aggregate_after > max_aggregate:
            reasons.append("MAX_AGGREGATE_NOTIONAL")

        available_margin = float(account.get("available_margin") or 0)
        equity = float(account.get("equity") or account.get("balance") or 0)
        margin_base = available_margin if available_margin > 0 else equity
        max_leverage = min(5.0, float(policy.get("max_leverage", 1)))
        if margin_base > 0 and aggregate_after > margin_base * max_leverage:
            reasons.append("EXPOSURE_EXCEEDS_MARGIN")
        elif margin_base <= 0 and aggregate_after > 0:
            reasons.append("MARGIN_UNAVAILABLE")
        return {
            "reasons": reasons,
            "position_notional": round(position_notional, 8),
            "order_notional": round(order_notional, 8),
            "aggregate_after": round(aggregate_after, 8),
            "available_margin": round(margin_base, 8),
        }

    def kill_switch(self, enabled: bool) -> dict:
        self.global_kill_switch = enabled
        return {"enabled": enabled, "live_execution": False}

    def pause_opening(self, account_id: str) -> None:
        """Freeze new (non reduce-only) openings for an account until resumed."""
        self.pause_opening_accounts.add(account_id)

    def resume_opening(self, account_id: str) -> None:
        self.pause_opening_accounts.discard(account_id)

    def sync_paused_runs(self, runs: list[dict]) -> None:
        self.paused_run_ids = {
            run["id"] for run in runs if run.get("status") == "PAUSED"
        }
