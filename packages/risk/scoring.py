from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from packages.data.base import MarketQuote


RISK_LOW = "risk_low"
RISK_MEDIUM = "risk_medium"
RISK_HIGH = "risk_high"
RISK_EXTREME = "risk_extreme"


@dataclass(frozen=True)
class RiskScoreBreakdown:
    total: int
    bucket: str
    realized_volatility: int
    liquidity: int
    funding_rate: int
    open_interest: int
    liquidation_clusters: int
    concentration: int
    correlation: int
    drawdown: int
    macro_regime: int
    event_risk: int
    counterparty_exchange: int
    data_quality: int

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "bucket": self.bucket,
            "realized_volatility": self.realized_volatility,
            "liquidity": self.liquidity,
            "funding_rate": self.funding_rate,
            "open_interest": self.open_interest,
            "liquidation_clusters": self.liquidation_clusters,
            "concentration": self.concentration,
            "correlation": self.correlation,
            "drawdown": self.drawdown,
            "macro_regime": self.macro_regime,
            "event_risk": self.event_risk,
            "counterparty_exchange": self.counterparty_exchange,
            "data_quality": self.data_quality,
        }


def _clamp_score(value: float, upper: int) -> int:
    return max(0, min(upper, int(round(value))))


def risk_bucket(score: int) -> str:
    if score <= 30:
        return RISK_LOW
    if score <= 60:
        return RISK_MEDIUM
    if score <= 80:
        return RISK_HIGH
    return RISK_EXTREME


def data_quality_risk(quote: MarketQuote, as_of: datetime | None = None, freshness_minutes: int = 5) -> int:
    if quote.timestamp is None:
        return 25
    as_of = as_of or datetime.now(timezone.utc)
    quote_time = quote.timestamp
    if quote_time.tzinfo is None:
        quote_time = quote_time.replace(tzinfo=timezone.utc)
    age_seconds = max(0.0, (as_of - quote_time).total_seconds())
    freshness_seconds = max(1, freshness_minutes * 60)
    if age_seconds <= freshness_seconds:
        return 0
    if age_seconds <= freshness_seconds * 4:
        return 12
    return 25


def risk_score_breakdown_for_quote(
    quote: MarketQuote,
    *,
    as_of: datetime | None = None,
    freshness_minutes: int = 5,
    concentration: float = 0.0,
    correlation: float = 0.0,
    drawdown: float = 0.0,
    macro_regime_stress: float = 0.0,
    event_risk: float = 0.0,
    counterparty_exchange_risk: float = 0.0,
) -> RiskScoreBreakdown:
    realized_volatility = _clamp_score(quote.volatility * 42, 25)

    if quote.volume_24h <= 0:
        liquidity = 20
    else:
        turnover_ratio = quote.volume_24h / max(quote.market_cap, 1.0)
        liquidity = _clamp_score((0.08 - min(turnover_ratio, 0.08)) * 180, 18)

    funding_rate = _clamp_score(abs(quote.funding_rate) * 1500, 22)
    oi_ratio = quote.open_interest / max(quote.volume_24h, 1.0)
    open_interest = _clamp_score(oi_ratio * 12, 14)
    liquidation_ratio = quote.liquidation_estimate / max(quote.volume_24h, 1.0)
    liquidation_clusters = _clamp_score(liquidation_ratio * 120, 10)
    concentration_component = _clamp_score(concentration * 15, 10)
    correlation_component = _clamp_score(max(0.0, correlation) * 10, 8)
    drawdown_component = _clamp_score(abs(drawdown) * 60, 10)
    macro_component = _clamp_score(macro_regime_stress * 12, 10)
    event_component = _clamp_score(event_risk * 12, 10)
    counterparty_component = _clamp_score(counterparty_exchange_risk * 12, 10)
    quality_component = data_quality_risk(quote, as_of=as_of, freshness_minutes=freshness_minutes)

    total = 8 + sum(
        [
            realized_volatility,
            liquidity,
            funding_rate,
            open_interest,
            liquidation_clusters,
            concentration_component,
            correlation_component,
            drawdown_component,
            macro_component,
            event_component,
            counterparty_component,
            quality_component,
        ]
    )
    total = max(0, min(100, total))
    return RiskScoreBreakdown(
        total=total,
        bucket=risk_bucket(total),
        realized_volatility=realized_volatility,
        liquidity=liquidity,
        funding_rate=funding_rate,
        open_interest=open_interest,
        liquidation_clusters=liquidation_clusters,
        concentration=concentration_component,
        correlation=correlation_component,
        drawdown=drawdown_component,
        macro_regime=macro_component,
        event_risk=event_component,
        counterparty_exchange=counterparty_component,
        data_quality=quality_component,
    )


def risk_score_for_quote(quote: MarketQuote, *, as_of: datetime | None = None, freshness_minutes: int = 5) -> int:
    return risk_score_breakdown_for_quote(quote, as_of=as_of, freshness_minutes=freshness_minutes).total


def portfolio_risk_summary(quotes: list[MarketQuote]) -> str:
    avg = sum(risk_score_for_quote(q) for q in quotes) / max(len(quotes), 1)
    if avg >= 70:
        return "Elevated leverage and volatility; reduce size and demand confirmation."
    if avg >= 50:
        return "Moderate risk; favor liquid assets and explicit invalidation levels."
    return "Risk is controlled; avoid over-sizing because crypto beta can gap quickly."
