from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.services.entitlement_service import get_user_entitlement
from apps.api.services.market_intelligence_service import MARKET_INTELLIGENCE_MAX_AGE, fresh_or_create_intelligence
from apps.api.services.portfolio_service import portfolio_context
from packages.agents.llm.provider_factory import get_llm_provider
from packages.data.earnings_calendar import upcoming_earnings
from packages.data.trending import top_trending
from packages.database.models import AgentConversation, AgentMessage, MarketSnapshot, UserPreference


# Research Desk and the dashboard both render ``crypto_daily``.  Keeping this
# limit at the renderer boundary prevents a verbose model response from
# becoming a verbose notification.  Markdown markers count toward the budget.
DAILY_BRIEF_MAX_CHARS_ZH = 200
DAILY_BRIEF_MAX_WORDS_EN = 120
_HYPERLIQUID_BREADTH_CACHE_SECONDS = 15
_hyperliquid_breadth_cache: tuple[float, dict] = (0.0, {})


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _recent_conversation_topics(db: Session, user_id: str) -> list[str]:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    conversations = db.query(AgentConversation).filter(AgentConversation.user_id == user_id, AgentConversation.status == "active", AgentConversation.updated_at >= since).order_by(AgentConversation.updated_at.desc()).limit(5).all()
    topics: list[str] = []
    for conversation in conversations:
        messages = db.query(AgentMessage).filter(AgentMessage.conversation_id == conversation.id, AgentMessage.role == "user", AgentMessage.status == "completed").order_by(AgentMessage.created_at.desc()).limit(3).all()
        topics.extend(message.content[:120].replace("\n", " ") for message in messages if message.content.strip())
    return topics[:8]


def _trending_providers(allowed: set[str]) -> tuple[str, ...]:
    """Document providers a plan may see in the buzz section.

    X/Twitter buzz is reserved for plans whose entitlement includes it
    (Max and above); everyone else sees RSS/fintwit mentions only.
    """
    if "all" in allowed:
        return ("rss", "fintwit", "x-twitter")
    providers = [provider for provider in ("rss", "fintwit") if provider in allowed]
    if "x-twitter" in allowed or "x" in allowed:
        providers.append("x-twitter")
    return tuple(providers)


def _hyperliquid_top20_breadth() -> dict:
    """Summarize the active Hyperliquid perp universe for the daily brief.

    The console already uses Hyperliquid's public market feed.  This concise
    top-20 aggregation adds breadth (moves, funding and OI) to the report
    without dumping the full market table into a notification.  It is cached
    briefly because one shared brief can be rendered for many users at once.
    """
    global _hyperliquid_breadth_cache
    cached_at, cached = _hyperliquid_breadth_cache
    if cached and time.monotonic() - cached_at < _HYPERLIQUID_BREADTH_CACHE_SECONDS:
        return cached
    # Test and explicitly mocked environments must stay offline.  Production
    # still reads the live public feed; an unavailable live feed degrades to a
    # clearly marked missing breadth input instead of synthetic data.
    if os.getenv("ENABLE_MOCK_MARKET_DATA", "false").lower() == "true":
        return {"available": False, "market_count": 0}
    try:
        from packages.data.hyperliquid_provider import HyperliquidProvider

        markets = HyperliquidProvider().get_top_markets(limit=20)
    except Exception:
        payload = {"available": False, "market_count": 0}
        _hyperliquid_breadth_cache = (time.monotonic(), payload)
        return payload
    if not markets:
        payload = {"available": False, "market_count": 0}
        _hyperliquid_breadth_cache = (time.monotonic(), payload)
        return payload

    with_change = [quote for quote in markets if quote.change_24h is not None]
    leaders = sorted(with_change, key=lambda quote: quote.change_24h or 0, reverse=True)[:3]
    laggards = sorted(with_change, key=lambda quote: quote.change_24h or 0)[:3]
    oi_leaders = sorted(markets, key=lambda quote: quote.open_interest_usd or 0, reverse=True)[:3]
    funding_extremes = sorted(markets, key=lambda quote: abs(quote.funding_rate), reverse=True)[:3]

    def row(quote) -> dict:
        return {
            "symbol": quote.symbol,
            "change_24h": quote.change_24h,
            "funding_rate": quote.funding_rate,
            "open_interest_usd": quote.open_interest_usd,
            "volume_24h": quote.volume_24h,
        }

    payload = {
        "available": True,
        "market_count": len(markets),
        "source": "Hyperliquid public perps, top 20 by 24h notional",
        "as_of": max(quote.timestamp for quote in markets).astimezone(timezone.utc).isoformat(),
        "up_count": sum(1 for quote in with_change if (quote.change_24h or 0) > 0),
        "down_count": sum(1 for quote in with_change if (quote.change_24h or 0) < 0),
        "unchanged_or_unavailable_count": len(markets) - sum(1 for quote in with_change if (quote.change_24h or 0) != 0),
        "positive_funding_count": sum(1 for quote in markets if quote.funding_rate > 0),
        "negative_funding_count": sum(1 for quote in markets if quote.funding_rate < 0),
        "total_volume_24h": round(sum(quote.volume_24h for quote in markets), 2),
        "leaders": [row(quote) for quote in leaders],
        "laggards": [row(quote) for quote in laggards],
        "open_interest_leaders": [row(quote) for quote in oi_leaders],
        "funding_extremes": [row(quote) for quote in funding_extremes],
    }
    _hyperliquid_breadth_cache = (time.monotonic(), payload)
    return payload


def _compact_daily_brief(content: str, language: str) -> str:
    """Enforce the Research Desk's short-form daily-brief promise."""
    normalized = "\n".join(line.rstrip() for line in content.strip().splitlines())
    if language == "zh":
        if len(normalized) <= DAILY_BRIEF_MAX_CHARS_ZH:
            return normalized
        return normalized[: DAILY_BRIEF_MAX_CHARS_ZH - 1].rstrip("，、；：.。;: ") + "…"

    words = normalized.split()
    if len(words) <= DAILY_BRIEF_MAX_WORDS_EN:
        return normalized
    return " ".join(words[:DAILY_BRIEF_MAX_WORDS_EN]).rstrip(".,;: ") + "…"


def gather_context(db: Session, user_id: str, language: str) -> dict:
    intelligence = fresh_or_create_intelligence(db)
    snapshots = db.query(MarketSnapshot).filter(MarketSnapshot.id.in_(intelligence.source_snapshot_ids or [])).all()
    preference = db.query(UserPreference).filter_by(user_id=user_id).one_or_none()
    portfolio = portfolio_context(db, user_id)
    created_at = intelligence.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    today = datetime.now(timezone.utc).date()
    allowed_sources = set(get_user_entitlement(db, user_id)["allowed_data_sources"])
    now = datetime.now(timezone.utc)
    latest_snapshot_at = max((_as_utc(row.timestamp) for row in snapshots), default=_as_utc(created_at))
    return {
        "language": language,
        "shared_intelligence_id": intelligence.id,
        "market_regime": intelligence.market_regime,
        "market_summary": intelligence.summary_markdown,
        "market_data_as_of": latest_snapshot_at.isoformat(),
        # The snapshot timestamp, rather than merely the database row's
        # creation time, decides whether the numbers may support a new brief.
        "market_stale": now - latest_snapshot_at > MARKET_INTELLIGENCE_MAX_AGE,
        "quotes": [{"symbol": row.asset_id, "price": row.price, "funding_rate": row.funding_rate, "open_interest": row.open_interest, "open_interest_usd": round(row.open_interest * row.price, 2) if row.open_interest and row.price else None, "source_timestamp": row.timestamp.astimezone(timezone.utc).isoformat()} for row in snapshots],
        "hyperliquid_top20_breadth": _hyperliquid_top20_breadth(),
        "upcoming_earnings": upcoming_earnings(today, days=7, locale=language),
        "trending_symbols": top_trending(db, hours=24, limit=5, providers=_trending_providers(allowed_sources)),
        "portfolio": portfolio,
        "portfolio_shared_with_llm": bool(preference.include_portfolio_in_ai) if preference else True,
        "recent_topics": _recent_conversation_topics(db, user_id),
    }


def generate_daily_brief(db: Session, user_id: str, language: str) -> str:
    context = gather_context(db, user_id, language)
    if context["market_stale"]:
        raise RuntimeError("DAILY_BRIEF_MARKET_DATA_STALE")
    if not context["portfolio_shared_with_llm"]:
        return _local_brief(context, language, "")
    if language == "zh":
        language_instruction = "全部标题、正文、项目符号和标签都必须使用简体中文。除资产代码和专有名词外，不得输出英文标题或英文段落。"
        structure = """## 今日判断
一句话给出风险取向；必须同时参考 BTC/ETH/HYPE 与 hyperliquid_top20_breadth，不要只根据单一资产下结论。

## 关注
恰好两条短项目：只选最重要的广度、资金费率、持仓或新闻变化；每条必须有一个可观察数字或明确条件。

## 风险线
一条最关键的失效条件或拥挤风险。"""
        portfolio_instruction = "如真实组合已连接，只能把一个与组合直接相关的观察替换进“关注”两条之一；不要新增组合章节。" if context["portfolio"]["connected"] else "不要新增组合、NAV、集中度或缺少组合章节；这是一份纯市场简报。"
        data_quality_instruction = "仅在关键数据不可用或过期时，将其合并进“风险线”一句；不要新增数据质量章节。"
        length_instruction = "全部 Markdown（包含标题、符号和标点）严格不超过 200 个字符。不要列出完整财报名单、热议清单或 Top 20；只给结论、两条证据和一条风险线。"
    else:
        language_instruction = "Write every heading, sentence, bullet, and label in clear English. Do not output Chinese headings or prose."
        structure = """## Today's view
One sentence for the risk posture. It must use BTC/ETH/HYPE and hyperliquid_top20_breadth rather than a single asset.

## Focus
Exactly two short bullets. Choose only the most decision-relevant breadth, funding, OI, or news changes; each must cite one observable number or condition.

## Risk line
One key invalidation or crowding risk."""
        portfolio_instruction = "If a real portfolio is connected, replace only one Focus bullet with a directly relevant portfolio observation; do not add a portfolio section." if context["portfolio"]["connected"] else "Do not include portfolio, NAV, concentration, or missing-portfolio text. This is a market-only brief."
        data_quality_instruction = "If critical data is stale or unavailable, fold it into the one Risk line; do not add a data-quality section."
        length_instruction = "Keep the complete Markdown under 120 words. Do not list full earnings, trending, or Top-20 tables: give only the view, two evidence points, and one risk line."
    prompt = f"""Create a premium, user-facing daily market brief for PureGamma. {language_instruction}

Return Markdown only. Do not use tables, raw JSON, ISO timestamps, internal field names, boilerplate disclaimers, or headings such as Market Facts / Portfolio Facts / Inference. Do not repeat the title. Never invent prices, portfolio data, sources, or causal certainty. Use only the supplied context. State uncertainty plainly. Do not give execution instructions.

Use exactly this structure:
{structure}

{portfolio_instruction}
Omit unavailable metrics rather than describing their absence.

{data_quality_instruction}

{length_instruction}

{json.dumps(context, ensure_ascii=False, default=str)}"""
    try:
        generated = get_llm_provider().complete(prompt, task_type="daily_market_report", locale=language, user_id=user_id, db=db)
    except Exception as exc:
        if get_settings().app_environment.lower() == "production":
            raise RuntimeError("DAILY_BRIEF_MODEL_UNAVAILABLE") from exc
        return _local_brief(context, language, "")
    return _compact_daily_brief(generated, language)


def _local_brief(context: dict, language: str, disclaimer: str) -> str:
    quotes = {str(item.get("symbol") or "").upper(): item for item in context.get("quotes") or []}
    breadth = context.get("hyperliquid_top20_breadth") or {}
    available_breadth = bool(breadth.get("available"))

    def quote_line(symbol: str, zh: bool) -> str | None:
        quote = quotes.get(symbol)
        if not quote or quote.get("price") is None:
            return None
        price = float(quote["price"])
        funding = quote.get("funding_rate")
        if funding is None:
            return f"{symbol} ${price:,.0f}"
        return f"{symbol} ${price:,.0f}，资金 {float(funding):.3%}" if zh else f"{symbol} ${price:,.0f}, funding {float(funding):.3%}"

    def breadth_line(zh: bool) -> str | None:
        if not available_breadth:
            return None
        total = int(breadth.get("market_count") or 0)
        up = int(breadth.get("up_count") or 0)
        down = int(breadth.get("down_count") or 0)
        positive = int(breadth.get("positive_funding_count") or 0)
        negative = int(breadth.get("negative_funding_count") or 0)
        return (
            f"Hyperliquid Top{total}：{up}涨/{down}跌，资金 {positive}正/{negative}负"
            if zh
            else f"Hyperliquid top {total}: {up} up / {down} down, funding {positive} positive / {negative} negative"
        )

    def crowding_line(zh: bool) -> str | None:
        extremes = breadth.get("funding_extremes") or []
        if not extremes:
            return None
        item = extremes[0]
        symbol = str(item.get("symbol") or "")
        funding = item.get("funding_rate")
        if not symbol or funding is None:
            return None
        return (
            f"{symbol} 资金费率 {float(funding):.3%}，留意拥挤波动"
            if zh
            else f"{symbol} funding {float(funding):.3%}: watch crowding"
        )

    primary_quotes = [line for line in (quote_line("BTC", language == "zh"), quote_line("ETH", language == "zh"), quote_line("HYPE", language == "zh")) if line]
    breadth_summary = breadth_line(language == "zh")
    crowding = crowding_line(language == "zh")
    if language == "zh":
        view = f"{context['market_regime']}。"
        if breadth_summary:
            view += f" {breadth_summary}。"
        lines = ["## 今日判断", view, "", "## 关注"]
        lines.append("- " + (primary_quotes[0] if primary_quotes else "主流市场报价暂不可用"))
        lines.append("- " + (crowding or breadth_summary or "Hyperliquid 广度数据暂不可用"))
        lines.extend(["", "## 风险线"])
        lines.append("- 若涨跌广度转弱且资金费率继续扩张，警惕杠杆回撤。")
    else:
        view = f"{context['market_regime']}."
        if breadth_summary:
            view += f" {breadth_summary}."
        lines = ["## Today's view", view, "", "## Focus"]
        lines.append("- " + (primary_quotes[0] if primary_quotes else "Core market quotes are unavailable"))
        lines.append("- " + (crowding or breadth_summary or "Hyperliquid breadth data is unavailable"))
        lines.extend(["", "## Risk line"])
        lines.append("- Watch for weakening breadth alongside expanding funding: leverage can amplify a reversal.")
    return _compact_daily_brief("\n".join(lines).rstrip() + f"\n\n{disclaimer}", language)
