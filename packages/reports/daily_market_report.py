from __future__ import annotations

from packages.data.base import MarketQuote
from packages.reports.templates import disclaimer_for
from packages.risk.scoring import portfolio_risk_summary, risk_score_for_quote
from packages.strategies.registry import generate_playbooks


def render_daily_report(market_regime: str, quotes: list[MarketQuote], signals: list[dict], language: str = "en") -> str:
    if language == "zh":
        return render_daily_report_zh(market_regime, quotes, signals)
    lines = [
        "# PureGamma Daily Crypto Brief",
        "",
        "## Market Regime",
        market_regime,
        "",
        "## Key Signals",
    ]
    for signal in signals[:5]:
        lines.append(f"- **{signal['asset']} {signal['direction']}**: {signal['thesis']}")
    quote_map = {quote.symbol: quote for quote in quotes}
    for symbol in ["BTC", "ETH", "SOL", "HYPE"]:
        quote = quote_map.get(symbol)
        if not quote:
            continue
        lines.extend(
            [
                "",
                f"## {symbol}",
                f"Price: ${quote.price:,.2f}. Funding: {quote.funding_rate:.3%}. Risk score: {risk_score_for_quote(quote)}.",
            ]
        )
    lines.extend(["", "## MSTR / STRC"])
    for symbol in ["MSTR", "STRC"]:
        quote = quote_map.get(symbol)
        if quote:
            lines.append(f"- {symbol}: ${quote.price:,.2f}, sentiment {quote.sentiment_score:.2f}.")
    lines.extend(
        [
            "",
            "## Event Watch",
            "ETF flow, funding resets, liquidation clusters, MSTR premium shifts, and STRC issuer events remain the main watch items.",
            "",
            "## Risk",
            portfolio_risk_summary(quotes),
            "",
            "## Playbook",
            generate_playbooks()[0]["thesis"],
            "",
            "## Disclaimer",
            disclaimer_for(language),
        ]
    )
    return "\n".join(lines)


def render_daily_report_zh(market_regime: str, quotes: list[MarketQuote], signals: list[dict]) -> str:
    lines = [
        "# PureGamma 每日加密市场简报",
        "",
        "## 市场状态",
        market_regime,
        "",
        "## 重点信号",
    ]
    for signal in signals[:5]:
        lines.append(f"- **{signal['asset']} {signal['direction']}**：{signal['thesis']}")
    quote_map = {quote.symbol: quote for quote in quotes}
    for symbol in ["BTC", "ETH", "SOL", "HYPE"]:
        quote = quote_map.get(symbol)
        if not quote:
            continue
        lines.extend(
            [
                "",
                f"## {symbol}",
                f"价格：${quote.price:,.2f}。资金费率：{quote.funding_rate:.3%}。风险评分：{risk_score_for_quote(quote)}。",
            ]
        )
    lines.extend(["", "## MSTR / STRC"])
    for symbol in ["MSTR", "STRC"]:
        quote = quote_map.get(symbol)
        if quote:
            lines.append(f"- {symbol}：${quote.price:,.2f}，情绪评分 {quote.sentiment_score:.2f}。")
    lines.extend(
        [
            "",
            "## 事件观察",
            "ETF 资金流、资金费率重置、清算簇、MSTR 溢价变化与 STRC 发行人事件仍是主要观察项。",
            "",
            "## 风险",
            portfolio_risk_summary(quotes),
            "",
            "## 策略框架",
            generate_playbooks()[0]["thesis"],
            "",
            "## 披露",
            disclaimer_for("zh"),
        ]
    )
    return "\n".join(lines)
