from __future__ import annotations

from apps.api.services.report_service import create_daily_report
from packages.agents.llm_client import LLMClient, LLM_CALL_LOG
from packages.data.mock_provider import MockMarketDataProvider
from packages.reports.daily_market_report import render_daily_report


def test_daily_report_generated_with_disclaimer(db, demo_user):
    report = create_daily_report(db, demo_user.id)

    assert report.report_type == "daily_market_report"


def test_report_cache_returns_same_daily_report(db, demo_user):
    first = create_daily_report(db, demo_user.id)
    second = create_daily_report(db, demo_user.id)

    assert first.id == second.id


def test_llm_provider_mock_works_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    before = len(LLM_CALL_LOG)

    completion = LLMClient().complete("qa-test", "Summarize BTC risk.")

    assert "Mock LLM synthesis" in completion
    assert len(LLM_CALL_LOG) == before + 1


def test_agent_report_strict_copy_avoids_direct_buy_sell_command():
    quotes = MockMarketDataProvider().get_snapshot(["BTC"])
    content = render_daily_report(
        "Mixed",
        quotes,
        [{"asset": "BTC", "direction": "long_watch", "thesis": "Watch liquidity", "catalyst": "Breakout", "invalidation": "Failed range"}],
    )
    lowered = content.lower()

    assert "buy now" not in lowered
    assert "sell now" not in lowered
