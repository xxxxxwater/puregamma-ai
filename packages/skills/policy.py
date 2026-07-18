from __future__ import annotations

# Imported Skills are declarative in phase one. Even when a manifest is marked
# execution-sensitive it cannot import or execute code, reach secrets, or submit
# an order. Mutating tools remain reserved for reviewed official releases.
READ_ONLY_SKILL_TOOLS = {
    "get_market_quote",
    "get_market_history",
    "get_recent_news",
    "search_news",
    "search_source_documents",
    "get_defi_protocol_metrics",
    "get_chain_metrics",
    "get_onchain_snapshot",
    "get_data_source_status",
    "run_nautilus_backtest",
    "list_research_strategies",
    "get_strategy_performance",
    "get_sentiment_context",
    "get_account_snapshot",
    "get_position_snapshot",
    "get_open_orders",
    "get_strategy_status",
    "get_options_context",
    "get_earnings_gamma",
}

REVIEWED_OFFICIAL_TOOLS = READ_ONLY_SKILL_TOOLS | {
    "create_strategy_draft",
    "modify_strategy_draft",
    "validate_strategy",
    "backtest_strategy",
    "create_paper_run",
    "create_shadow_run",
    "preview_strategy_activation",
    "generate_order_preview",
}

# Explicitly excluded from every imported bundle. Runtime state transitions are
# performed only by the existing audited control plane, never by Skill content.
NEVER_IMPORTED_TOOLS = {
    "activate_strategy",
    "pause_strategy",
    "resume_strategy",
    "stop_strategy",
    "reconcile_account",
}

ALLOWED_ASSET_CLASSES = {
    "crypto",
    "options",
    "equities",
    "portfolio",
    "defi",
    "macro",
    "multi_asset",
}

ALLOWED_DATA_SOURCES = {
    "market",
    "rss",
    "fintwit",
    "x",
    "x-twitter",
    "bloomberg",
    "portfolio",
    "options",
    "onchain",
    "defillama",
}

TOOL_DATA_SOURCE_REQUIREMENTS = {
    "get_market_quote": "market",
    "get_market_history": "market",
    "get_account_snapshot": "portfolio",
    "get_position_snapshot": "portfolio",
    "get_open_orders": "portfolio",
    "get_options_context": "options",
    "get_onchain_snapshot": "onchain",
    "get_chain_metrics": "onchain",
}
