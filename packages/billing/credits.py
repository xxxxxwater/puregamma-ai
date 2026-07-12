from __future__ import annotations


CREDIT_COSTS: dict[str, int] = {
    "daily_market_report": 10,
    "event_report": 5,
    "sentiment_scan": 8,
    "x_sentiment_scan": 20,
    "onchain_scan": 12,
    "backtest": 25,
    "playbook_generation": 30,
    "portfolio_daily_brief": 10,
    "daily_combined_imessage": 15,
    "deepseek_report_generation": 10,
    "deepseek_playbook_generation": 30,
    "telegram_alert": 1,
    "slack_alert": 1,
    "email_alert": 1,
    "imessage_alert": 3,
    "strategy_generation": 5,
    "strategy_modification": 2,
    "strategy_activation": 5,
    "runtime_reconciliation": 2,
    "manual_order_preview": 1,
    "agent_chat_basic": 2,
    "agent_market_research": 3,
    "agent_news_research": 3,
    "agent_portfolio_analysis": 5,
    "agent_advanced_data": 5,
    "agent_deep_research": 15,
    "agent_luna_research": 20,
}


HIGH_COST_ACTIONS = {"x_sentiment_scan", "onchain_scan", "backtest", "playbook_generation", "portfolio_daily_brief", "daily_combined_imessage", "deepseek_report_generation", "deepseek_playbook_generation", "strategy_generation", "strategy_activation", "runtime_reconciliation", "manual_order_preview", "agent_luna_research"}


def cost_for(action: str) -> int:
    return CREDIT_COSTS[action]
