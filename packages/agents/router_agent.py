from __future__ import annotations


class RouterAgent:
    KEYWORDS = {
        "daily_report": ("daily", "brief", "日报", "研报"),
        "event_analysis": ("event", "catalyst", "事件"),
        "signal_scan": ("signal", "scan", "信号"),
        "backtest": ("backtest", "回测"),
        "playbook_generation": ("playbook", "策略"),
        "alert_generation": ("alert", "通知", "推送"),
    }

    def route(self, message: str) -> str:
        normalized = message.lower()
        for task, terms in self.KEYWORDS.items():
            if any(term in normalized for term in terms):
                return task
        return "daily_report"
