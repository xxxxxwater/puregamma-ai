from __future__ import annotations

from packages.strategies.signal_spec import (
    READINESS_RESEARCH_ONLY,
    calculate_signal_confidence,
    can_emit_actionable_language,
    get_default_signal_specs,
    validate_research_language,
)


def test_signal_confidence_declines_when_required_data_is_missing():
    full = calculate_signal_confidence(
        raw_score=0.82,
        required_data=["OHLCV", "funding", "open_interest"],
        available_data=["OHLCV", "funding", "open_interest"],
        risk_score=45,
        backtest_quality="validated",
    )
    missing = calculate_signal_confidence(
        raw_score=0.82,
        required_data=["OHLCV", "funding", "open_interest"],
        available_data=["OHLCV"],
        risk_score=45,
        backtest_quality="validated",
    )
    assert missing < full


def test_kol_sentiment_alone_cannot_create_high_confidence_signal():
    confidence = calculate_signal_confidence(
        raw_score=0.95,
        required_data=["KOL_sentiment"],
        available_data=["KOL_sentiment"],
        risk_score=25,
        kol_sentiment_only=True,
        backtest_quality="validated",
    )
    assert confidence <= 0.35


def test_default_signal_specs_include_required_fields():
    specs = get_default_signal_specs()
    btc = specs["BTC momentum breakout"]
    assert btc.strategy_name == "BTC momentum breakout"
    assert btc.asset_universe == ["BTC"]
    assert btc.entry_condition
    assert btc.invalidation
    assert "Users bear all risks of using this service. The service provider is not responsible for any AI-generated content." in btc.disclaimers


def test_research_only_strategy_cannot_emit_actionable_language():
    assert not can_emit_actionable_language(READINESS_RESEARCH_ONLY, 0.9, [])
    assert not validate_research_language("Buy HYPE after the breakout.", READINESS_RESEARCH_ONLY)
