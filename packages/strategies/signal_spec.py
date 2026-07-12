from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


READINESS_MVP_READY = "MVP Ready"
READINESS_RESEARCH_ONLY = "Research-only"
READINESS_ENTERPRISE_ONLY = "Enterprise-only"
READINESS_DO_NOT_LAUNCH = "Do not launch"

ACTIONABLE_READINESS = {READINESS_MVP_READY, READINESS_ENTERPRISE_ONLY}
ACTIONABLE_LANGUAGE = (
    "buy",
    "sell",
    "enter",
    "exit",
    "go long",
    "go short",
    "add exposure",
    "trim",
    "increase position",
)


@dataclass(frozen=True)
class SignalSpec:
    strategy_name: str
    asset_universe: list[str]
    signal_type: str
    direction: str
    raw_score: float
    normalized_score: float
    confidence: float
    risk_score: int
    regime_filter: str
    entry_condition: str
    exit_condition: str
    invalidation: str
    data_freshness_requirement: str
    minimum_liquidity: float
    max_leverage_assumption: float
    timeframe: str
    source_data: list[str]
    disclaimers: list[str]
    readiness: str = READINESS_RESEARCH_ONLY
    missing_data_fields: list[str] = field(default_factory=list)
    kol_sentiment_only: bool = False
    regime_active: bool = True
    backtest_quality: str = "mock"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def actionable(self) -> bool:
        return can_emit_actionable_language(self.readiness, self.confidence, self.missing_data_fields)


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def normalize_score(raw_score: float, lower: float = -1.0, upper: float = 1.0) -> float:
    if upper <= lower:
        raise ValueError("upper must be greater than lower")
    return round(clamp((raw_score - lower) / (upper - lower)), 4)


def calculate_signal_confidence(
    *,
    raw_score: float,
    required_data: list[str],
    available_data: list[str],
    risk_score: int,
    regime_active: bool = True,
    kol_sentiment_only: bool = False,
    backtest_quality: str = "mock",
) -> float:
    """Conservative confidence score for research signals.

    Confidence is capped when the signal lacks data, is sentiment-only, sits
    outside its regime, or relies only on mock/insufficient backtests.
    """

    confidence = clamp(raw_score)
    available = set(available_data)
    missing = [item for item in required_data if item not in available]
    if missing:
        confidence -= min(0.35, 0.08 * len(missing))

    if risk_score >= 81:
        confidence = min(confidence, 0.4)
    elif risk_score >= 61:
        confidence = min(confidence, 0.55)

    if not regime_active:
        confidence = min(confidence, 0.35)

    if kol_sentiment_only:
        confidence = min(confidence, 0.35)

    if backtest_quality in {"none", "mock", "insufficient"}:
        confidence = min(confidence, 0.5)

    return round(clamp(confidence), 4)


def can_emit_actionable_language(readiness: str, confidence: float, missing_data_fields: list[str] | None = None) -> bool:
    if readiness not in ACTIONABLE_READINESS:
        return False
    if confidence < 0.55:
        return False
    if missing_data_fields:
        return False
    return True


def contains_actionable_language(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in ACTIONABLE_LANGUAGE)


def validate_research_language(text: str, readiness: str) -> bool:
    if readiness in {READINESS_RESEARCH_ONLY, READINESS_DO_NOT_LAUNCH}:
        return not contains_actionable_language(text)
    return True


DEFAULT_SIGNAL_SPECS: dict[str, SignalSpec] = {
    "BTC momentum breakout": SignalSpec(
        strategy_name="BTC momentum breakout",
        asset_universe=["BTC"],
        signal_type="trend_breakout",
        direction="long_watch",
        raw_score=0.66,
        normalized_score=0.66,
        confidence=0.62,
        risk_score=48,
        regime_filter="Risk-on or neutral crypto regime; BTC realized volatility below stress threshold.",
        entry_condition="Daily close above 20-day range high, confirmed after bar close with volume above 30-day median.",
        exit_condition="Close back inside breakout range, funding crowding, or stop based on ATR.",
        invalidation="Breakout level lost on rising volume or BTC dominance fails while market breadth weakens.",
        data_freshness_requirement="OHLCV <= 5 minutes for intraday, <= 1 bar for daily; funding/OI <= 30 minutes.",
        minimum_liquidity=500_000_000,
        max_leverage_assumption=1.0,
        timeframe="1-3 weeks",
        source_data=["OHLCV", "volume", "funding", "open_interest", "liquidations", "ETF_flow_proxy"],
        disclaimers=["Research signal only.", "Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.", "No live trading is enabled."],
        readiness=READINESS_MVP_READY,
        backtest_quality="insufficient",
    ),
    "ETH/BTC rotation": SignalSpec(
        strategy_name="ETH/BTC rotation",
        asset_universe=["ETH", "BTC"],
        signal_type="relative_strength",
        direction="relative_long_eth_short_btc_watch",
        raw_score=0.61,
        normalized_score=0.61,
        confidence=0.58,
        risk_score=54,
        regime_filter="BTC volatility declining and ETH/BTC reclaiming trend support.",
        entry_condition="ETH/BTC closes above 20-day moving average after BTC range compression.",
        exit_condition="ETH/BTC loses moving average or BTC dominance resumes upside breakout.",
        invalidation="ETH/BTC lower low with broad alt weakness.",
        data_freshness_requirement="Pair OHLCV <= 1 bar; funding/OI <= 30 minutes.",
        minimum_liquidity=300_000_000,
        max_leverage_assumption=1.0,
        timeframe="1-4 weeks",
        source_data=["ETH_BTC_OHLCV", "BTC_volatility", "funding", "open_interest", "market_breadth"],
        disclaimers=["Relative rotation research only.", "Users bear all risks of using this service. The service provider is not responsible for any AI-generated content."],
        readiness=READINESS_MVP_READY,
        backtest_quality="insufficient",
    ),
    "SOL/HYPE high beta rotation": SignalSpec(
        strategy_name="SOL/HYPE high beta rotation",
        asset_universe=["SOL", "HYPE"],
        signal_type="high_beta_relative_strength",
        direction="long_watch",
        raw_score=0.56,
        normalized_score=0.56,
        confidence=0.44,
        risk_score=68,
        regime_filter="Only active during broad risk-on with contained funding and improving breadth.",
        entry_condition="SOL or HYPE relative strength turns positive for two sessions after volatility contraction.",
        exit_condition="Funding or basis becomes crowded, trend support breaks, or BTC regime turns risk-off.",
        invalidation="Failed retest with broad alt weakness and rising liquidations.",
        data_freshness_requirement="OHLCV <= 5 minutes; funding/OI/liquidations <= 15 minutes.",
        minimum_liquidity=150_000_000,
        max_leverage_assumption=1.0,
        timeframe="3-10 days",
        source_data=["OHLCV", "relative_strength", "funding", "open_interest", "liquidations", "market_breadth"],
        disclaimers=["High beta research only.", "Not suitable for high-confidence signals in MVP."],
        readiness=READINESS_RESEARCH_ONLY,
        backtest_quality="mock",
    ),
    "HYPE trend following": SignalSpec(
        strategy_name="HYPE trend following",
        asset_universe=["HYPE"],
        signal_type="trend_following",
        direction="long_watch",
        raw_score=0.53,
        normalized_score=0.53,
        confidence=0.4,
        risk_score=74,
        regime_filter="Risk-on crypto regime with stable exchange/protocol activity and non-stressed funding.",
        entry_condition="Higher high after volatility contraction with funding below stress threshold.",
        exit_condition="Trend support fails, liquidations cluster near price, or vertical extension appears.",
        invalidation="Loss of 7-day trend support with rising OI and negative breadth.",
        data_freshness_requirement="OHLCV/funding/OI <= 5 minutes; protocol metrics <= 1 day.",
        minimum_liquidity=75_000_000,
        max_leverage_assumption=1.0,
        timeframe="2-8 days",
        source_data=["OHLCV", "funding", "open_interest", "liquidations", "protocol_metrics"],
        disclaimers=["Research-only due to liquidity and data quality risk."],
        readiness=READINESS_RESEARCH_ONLY,
        backtest_quality="mock",
    ),
    "MSTR premium / BTC proxy trade": SignalSpec(
        strategy_name="MSTR premium / BTC proxy trade",
        asset_universe=["MSTR", "BTC"],
        signal_type="cross_market_proxy",
        direction="proxy_watch",
        raw_score=0.5,
        normalized_score=0.5,
        confidence=0.38,
        risk_score=70,
        regime_filter="BTC trend supportive and US equity liquidity stable.",
        entry_condition="BTC breakout with MSTR premium stable or expanding after equity market open.",
        exit_condition="Premium compresses despite BTC strength or equity risk regime deteriorates.",
        invalidation="BTC loses breakout, MSTR underperforms BTC materially, or premium data is stale.",
        data_freshness_requirement="BTC <= 5 minutes, MSTR equity quote <= 15 minutes, premium estimate <= 1 day.",
        minimum_liquidity=100_000_000,
        max_leverage_assumption=1.0,
        timeframe="1-3 weeks",
        source_data=["BTC_OHLCV", "MSTR_equity_price", "premium_discount", "equity_regime"],
        disclaimers=["Cross-market research only.", "Equity borrow/tax/session risks are not modeled in MVP."],
        readiness=READINESS_RESEARCH_ONLY,
        backtest_quality="insufficient",
    ),
    "STRC event-driven credit trade": SignalSpec(
        strategy_name="STRC event-driven credit trade",
        asset_universe=["STRC"],
        signal_type="event_driven_credit",
        direction="credit_watch",
        raw_score=0.42,
        normalized_score=0.42,
        confidence=0.22,
        risk_score=63,
        regime_filter="Issuer-specific credit data is fresh, liquid, and legally usable.",
        entry_condition="Credit spread widens without matching deterioration in issuer or collateral quality.",
        exit_condition="Spread normalizes, issuer risk rises, or event catalyst resolves.",
        invalidation="Issuer stress, liquidity break, stale spread data, or BTC collateral shock.",
        data_freshness_requirement="Issuer events <= publication timestamp; quotes/spreads <= 1 day and source-verified.",
        minimum_liquidity=25_000_000,
        max_leverage_assumption=1.0,
        timeframe="2-6 weeks",
        source_data=["credit_spread", "issuer_events", "BTC_collateral_proxy", "liquidity"],
        disclaimers=["Do not launch without licensed credit data and issuer-risk review."],
        readiness=READINESS_DO_NOT_LAUNCH,
        backtest_quality="none",
    ),
    "basis funding arbitrage": SignalSpec(
        strategy_name="basis funding arbitrage",
        asset_universe=["BTC", "ETH", "SOL"],
        signal_type="market_neutral_carry",
        direction="market_neutral_watch",
        raw_score=0.58,
        normalized_score=0.58,
        confidence=0.36,
        risk_score=66,
        regime_filter="Exchange, borrow, and funding data are reliable; counterparty limits available.",
        entry_condition="Annualized funding or basis exceeds fee, slippage, borrow, and counterparty hurdle.",
        exit_condition="Carry compresses below hurdle, margin risk rises, or venue health deteriorates.",
        invalidation="Exchange withdrawal, borrow, liquidation, or settlement risk exceeds limit.",
        data_freshness_requirement="Funding/OI/order book <= 1 minute; borrow and venue status <= 1 day.",
        minimum_liquidity=500_000_000,
        max_leverage_assumption=1.0,
        timeframe="1 day-4 weeks",
        source_data=["funding", "basis", "order_book", "borrow", "fees", "venue_health"],
        disclaimers=["Enterprise-only research; requires venue risk controls and licensed data."],
        readiness=READINESS_ENTERPRISE_ONLY,
        backtest_quality="insufficient",
    ),
}


def get_default_signal_specs() -> dict[str, SignalSpec]:
    return dict(DEFAULT_SIGNAL_SPECS)


def load_strategy_specs(path: str | Path = "config/strategy_specs.yaml") -> dict[str, SignalSpec]:
    """Load YAML specs when PyYAML is installed; otherwise return vetted defaults."""

    config_path = Path(path)
    if not config_path.exists():
        return get_default_signal_specs()
    try:
        import yaml  # type: ignore
    except ImportError:
        return get_default_signal_specs()

    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    specs: dict[str, SignalSpec] = {}
    for item in loaded.get("strategies", []):
        spec = SignalSpec(**item)
        specs[spec.strategy_name] = spec
    return specs or get_default_signal_specs()
