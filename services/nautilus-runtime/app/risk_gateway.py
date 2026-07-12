from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone


class RuntimeRiskGateway:
    def __init__(self):
        self.global_kill_switch = False
        self.pause_opening_accounts: set[str] = set()
        self._order_times: dict[str, deque[datetime]] = defaultdict(deque)

    def evaluate(self, order: dict, policy: dict, account: dict) -> dict:
        reasons: list[str] = []
        if self.global_kill_switch:
            reasons.append("GLOBAL_KILL_SWITCH")
        if order["account_id"] in self.pause_opening_accounts and not order.get(
            "reduce_only"
        ):
            reasons.append("OPENING_PAUSED")
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
            },
        }

    def kill_switch(self, enabled: bool) -> dict:
        self.global_kill_switch = enabled
        return {"enabled": enabled, "live_execution": False}
