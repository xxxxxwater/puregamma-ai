"""Deterministic financial-language understanding for Agent and data products.

This module intentionally contains no LLM calls.  It normalizes user language
into stable entities and intents that can be audited, tested, and shared by the
Agent Runtime, Skills, reports, and future automation entry points.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass


LEXICON_VERSION = "2026.07.1"


@dataclass(frozen=True)
class QueryUnderstanding:
    intent: str
    assets: tuple[str, ...]
    asset_classes: tuple[str, ...]
    horizon: str | None
    locale: str
    confidence: float
    ambiguity: tuple[str, ...]

    def as_dict(self) -> dict:
        return {**asdict(self), "assets": list(self.assets), "asset_classes": list(self.asset_classes), "ambiguity": list(self.ambiguity), "lexicon_version": LEXICON_VERSION}


_ASSET_ALIASES: dict[str, tuple[str, tuple[str, ...]]] = {
    "BTC": ("crypto", (r"\bbtc\b", r"\bbitcoin\b", "比特币")),
    "ETH": ("crypto", (r"\beth\b", r"\bethereum\b", "以太坊")),
    "SOL": ("crypto", (r"\bsol\b", r"\bsolana\b")),
    "HYPE": ("crypto", (r"\bhype\b", r"\bhyperliquid\b")),
    "MSTR": ("equities", (r"\bmstr\b", r"\bmicrostrategy\b", r"\bstrategy inc\b")),
    "STRC": ("equities", (r"\bstrc\b",)),
    "SPY": ("equities", (r"\bspy\b", r"\bs&p\s*500\b", "标普500", "标普 500")),
    "QQQ": ("equities", (r"\bqqq\b", r"\bnasdaq\s*100\b", "纳斯达克100", "纳指100")),
}

_INTENT_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("strategy_control", ("activate", "start strategy", "pause", "resume", "stop strategy", "启动策略", "激活策略", "暂停策略", "恢复策略", "停止策略")),
    ("strategy_backtest", ("backtest", "回测")),
    ("strategy_research", ("strategy", "playbook", "策略", "交易系统")),
    ("deep_research", ("deep research", "full research", "investment memo", "深度研究", "完整研究", "投资备忘录")),
    ("portfolio_review", ("portfolio", "position", "allocation", "exposure", "pnl", "组合", "持仓", "仓位", "敞口", "盈亏")),
    ("options_analysis", ("option", "gamma", "delta", "theta", "vega", "implied volatility", "期权", "希腊字母", "隐含波动率", "波动率曲面")),
    ("source_check", ("verify source", "source check", "provenance", "freshness", "核验来源", "来源是否", "数据新鲜度", "出处")),
    ("news_research", ("news", "headline", "catalyst", "event", "新闻", "消息", "催化", "事件")),
    ("market_research", ("price", "quote", "market", "trend", "support", "resistance", "行情", "价格", "市场", "趋势", "支撑", "阻力")),
)

_HORIZONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("intraday", ("intraday", "today", "24h", "日内", "今天", "24小时")),
    ("short_term", ("this week", "next week", "7d", "一周", "本周", "下周", "短期")),
    ("medium_term", ("this month", "next month", "30d", "本月", "下个月", "中期")),
    ("long_term", ("long term", "year", "长期", "一年")),
)


def _contains(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def understand_query(query: str) -> QueryUnderstanding:
    normalized = " ".join(query.lower().split())
    locale = "zh" if re.search(r"[\u3400-\u9fff]", query) else "en"
    assets: list[str] = []
    asset_classes: list[str] = []
    for symbol, (asset_class, patterns) in _ASSET_ALIASES.items():
        if any(re.search(pattern, normalized, re.I) for pattern in patterns):
            assets.append(symbol)
            if asset_class not in asset_classes:
                asset_classes.append(asset_class)

    intent = "general_research"
    for candidate, terms in _INTENT_TERMS:
        if _contains(normalized, terms):
            intent = candidate
            break
    if intent == "general_research" and assets:
        intent = "market_research"

    horizon = next((name for name, terms in _HORIZONS if _contains(normalized, terms)), None)
    ambiguity: list[str] = []
    if intent in {"market_research", "news_research", "options_analysis"} and not assets:
        ambiguity.append("asset")
    if intent == "portfolio_review":
        asset_classes.append("portfolio") if "portfolio" not in asset_classes else None

    confidence = 0.95 if intent != "general_research" and assets else 0.82 if intent != "general_research" else 0.6
    return QueryUnderstanding(
        intent=intent,
        assets=tuple(assets),
        asset_classes=tuple(asset_classes),
        horizon=horizon,
        locale=locale,
        confidence=confidence,
        ambiguity=tuple(ambiguity),
    )
