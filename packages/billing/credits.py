from __future__ import annotations


CREDIT_COSTS: dict[str, int] = {
    "daily_market_report": 4,
    "event_report": 5,
    "sentiment_scan": 8,
    "x_sentiment_scan": 20,
    "onchain_scan": 12,
    "backtest": 50,
    "backtest_export": 50,
    "playbook_generation": 30,
    "portfolio_daily_brief": 8,
    "daily_combined_imessage": 15,
    "deepseek_report_generation": 10,
    "deepseek_playbook_generation": 30,
    "telegram_alert": 1,
    "slack_alert": 1,
    "email_alert": 1,
    "imessage_alert": 2,
    "push_alert": 1,
    "strategy_generation": 5,
    "strategy_modification": 2,
    "strategy_activation": 5,
    "runtime_reconciliation": 2,
    "manual_order_preview": 1,
    "agent_chat_basic": 2,
    "agent_market_research": 2,
    "agent_news_research": 2,
    "agent_portfolio_analysis": 2,
    "agent_advanced_data": 2,
    "agent_deep_research": 10,
    "agent_luna_research": 6,
    "private_secretary_reply": 20,
    "research_run": 20,
}


HIGH_COST_ACTIONS = {"x_sentiment_scan", "onchain_scan", "backtest", "backtest_export", "playbook_generation", "portfolio_daily_brief", "daily_combined_imessage", "deepseek_report_generation", "deepseek_playbook_generation", "strategy_generation", "strategy_activation", "runtime_reconciliation", "manual_order_preview", "agent_luna_research", "research_run"}


def cost_for(action: str) -> int:
    if action not in CREDIT_COSTS:
        raise KeyError(action)
    from packages.billing.metering import quote_credits

    return quote_credits(task_type=action, requested_model="default").credits
