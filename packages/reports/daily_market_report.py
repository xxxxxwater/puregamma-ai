from __future__ import annotations

from packages.data.base import MarketQuote
from packages.reports.templates import disclaimer_for
from packages.risk.scoring import portfolio_risk_summary


def render_daily_report(market_regime: str, quotes: list[MarketQuote], signals: list[dict], language: str = "en") -> str:
    if language == "zh":
        return _render_zh(market_regime, quotes, signals)
    return _render_en(market_regime, quotes, signals)


def _render_en(market_regime: str, quotes: list[MarketQuote], signals: list[dict]) -> str:
    lines = ["# PureGamma Daily Crypto Brief", "", f"**Regime:** {market_regime}"]
    quote_map = {q.symbol: q for q in quotes}
    for symbol in ["BTC", "ETH", "HYPE"]:
        q = quote_map.get(symbol)
        if q:
            lines.append(f"- {symbol}: ${q.price:,.2f} (sentiment {q.sentiment_score:.2f})")
    if signals:
        lines.append("")
        lines.append("**Key signals:**")
        for sig in signals[:3]:
            lines.append(f"- {sig['asset']} {sig['direction']}: {sig['thesis'][:120]}")
    lines.extend(["", f"**Risk:** {portfolio_risk_summary(quotes)}", "", disclaimer_for("en")])
    return "\n".join(lines)


def _render_zh(market_regime: str, quotes: list[MarketQuote], signals: list[dict]) -> str:
    lines = ["# PureGamma 每日简报", "", f"**市场状态:** {market_regime}"]
    quote_map = {q.symbol: q for q in quotes}
    for symbol in ["BTC", "ETH", "HYPE"]:
        q = quote_map.get(symbol)
        if q:
            lines.append(f"- {symbol}: ${q.price:,.2f}（情绪 {q.sentiment_score:.2f}）")
    if signals:
        lines.append("")
        lines.append("**重点信号:**")
        for sig in signals[:3]:
            lines.append(f"- {sig['asset']} {sig['direction']}: {sig['thesis'][:120]}")
    lines.extend(["", f"**风险:** {portfolio_risk_summary(quotes)}", "", disclaimer_for("zh")])
    return "\n".join(lines)
