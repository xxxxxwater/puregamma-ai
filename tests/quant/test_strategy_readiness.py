from __future__ import annotations

from packages.strategies.signal_spec import (
    READINESS_DO_NOT_LAUNCH,
    READINESS_ENTERPRISE_ONLY,
    READINESS_MVP_READY,
    READINESS_RESEARCH_ONLY,
    can_emit_actionable_language,
    load_strategy_specs,
)


def test_strategy_readiness_classification():
    specs = load_strategy_specs()
    assert specs["BTC momentum breakout"].readiness == READINESS_MVP_READY
    assert specs["ETH/BTC rotation"].readiness == READINESS_MVP_READY
    assert specs["HYPE trend following"].readiness == READINESS_RESEARCH_ONLY
    assert specs["STRC event-driven credit trade"].readiness == READINESS_DO_NOT_LAUNCH
    assert specs["basis funding arbitrage"].readiness == READINESS_ENTERPRISE_ONLY


def test_research_only_readiness_blocks_actionable_output_even_with_high_confidence():
    assert not can_emit_actionable_language(READINESS_RESEARCH_ONLY, 0.95, [])
