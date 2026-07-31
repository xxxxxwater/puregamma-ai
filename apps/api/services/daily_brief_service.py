from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.services.entitlement_service import get_user_entitlement
from apps.api.services.market_intelligence_service import latest_or_create_intelligence
from apps.api.services.portfolio_service import portfolio_context
from packages.agents.llm.provider_factory import get_llm_provider
from packages.data.earnings_calendar import upcoming_earnings
from packages.data.trending import top_trending
from packages.database.models import AgentConversation, AgentMessage, MarketSnapshot, UserPreference


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


def gather_context(db: Session, user_id: str, language: str) -> dict:
    intelligence = latest_or_create_intelligence(db)
    snapshots = db.query(MarketSnapshot).filter(MarketSnapshot.id.in_(intelligence.source_snapshot_ids or [])).all()
    preference = db.query(UserPreference).filter_by(user_id=user_id).one_or_none()
    portfolio = portfolio_context(db, user_id)
    created_at = intelligence.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    today = datetime.now(timezone.utc).date()
    allowed_sources = set(get_user_entitlement(db, user_id)["allowed_data_sources"])
    return {
        "language": language,
        "shared_intelligence_id": intelligence.id,
        "market_regime": intelligence.market_regime,
        "market_summary": intelligence.summary_markdown,
        "market_data_as_of": max((row.timestamp for row in snapshots), default=created_at).astimezone(timezone.utc).isoformat(),
        "market_stale": datetime.now(timezone.utc) - created_at.astimezone(timezone.utc) > timedelta(hours=8),
        "quotes": [{"symbol": row.asset_id, "price": row.price, "funding_rate": row.funding_rate, "open_interest": row.open_interest, "open_interest_usd": round(row.open_interest * row.price, 2) if row.open_interest and row.price else None, "source_timestamp": row.timestamp.astimezone(timezone.utc).isoformat()} for row in snapshots],
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
        structure = """## 今日市场判断
用一句明确、易懂的话说明市场状态和风险取向。

## 今日重点
恰好三个简短项目符号。每项指出资产或条件、可观察数据，以及它为何重要。

## 今日全网热议
列出 trending_symbols 中被提及最多的标的（含股票与加密），每项标注 24 小时提及次数；若 trending_symbols 为空则省略本节。

## 美股财报（未来一周）
按日期列出 upcoming_earnings 中的美股个股财报日期，保留“（预计）”标注；若 upcoming_earnings 为空则省略本节。

## 关键观察阈值
最多三个可量化条件，说明当前状态以及什么变化会改变判断。"""
        portfolio_instruction = "仅在已连接真实组合时加入 `## 我的组合`，最多给出三条简洁、个性化观察。" if context["portfolio"]["connected"] else "不要加入组合、NAV、集中度或缺少组合等章节；这是一份纯市场简报。"
        data_quality_instruction = "仅在数据过期、不完整或缺失时加入 `## 数据质量`，用一句自然中文说明新鲜度和来源。"
    else:
        language_instruction = "Write every heading, sentence, bullet, and label in clear English. Do not output Chinese headings or prose."
        structure = """## Today's view
One decisive, plain-language sentence describing the market regime and risk posture.

## What matters today
Exactly three short bullets. Each bullet names the asset or condition, cites the observable data point, and explains why it matters.

## Trending today
List the most-mentioned tickers from trending_symbols (stocks and crypto), each with its 24h mention count; omit this section when trending_symbols is empty.

## US earnings this week
List the upcoming_earnings entries by date for individual US stocks, keeping the "(est.)" label; omit this section when upcoming_earnings is empty.

## Watch levels
Up to three measurable conditions. State the current condition and what would change the view."""
        portfolio_instruction = "Include `## My portfolio` only because a real portfolio is connected, with at most three concise personalised observations." if context["portfolio"]["connected"] else "Do not include any portfolio, NAV, concentration, or missing-portfolio section. This is a market-only brief."
        data_quality_instruction = "Include `## Data quality` only when data is stale, partial, or missing, using one short human-readable line for freshness and sources."
    prompt = f"""Create a premium, user-facing daily market brief for PureGamma. {language_instruction}

Return Markdown only. Do not use tables, raw JSON, ISO timestamps, internal field names, boilerplate disclaimers, or headings such as Market Facts / Portfolio Facts / Inference. Do not repeat the title. Never invent prices, portfolio data, sources, or causal certainty. Use only the supplied context. State uncertainty plainly. Do not give execution instructions.

Use exactly this structure:
{structure}

{portfolio_instruction}
Omit unavailable metrics rather than describing their absence.

{data_quality_instruction}

{json.dumps(context, ensure_ascii=False, default=str)}"""
    try:
        generated = get_llm_provider().complete(prompt, task_type="daily_market_report", locale=language, user_id=user_id, db=db)
    except Exception as exc:
        if get_settings().app_environment.lower() == "production":
            raise RuntimeError("DAILY_BRIEF_MODEL_UNAVAILABLE") from exc
        return _local_brief(context, language, "")
    return generated.strip()


def _local_brief(context: dict, language: str, disclaimer: str) -> str:
    portfolio = context["portfolio"]
    quotes = context["quotes"]
    holdings = portfolio["top_holdings"]
    earnings = context.get("upcoming_earnings") or []
    trending = context.get("trending_symbols") or []
    if language == "zh":
        lines = ["PureGamma 每日加密市场简报 | 组合", "", "市场事实", f"市场状态：{context['market_regime']}。数据时间：{context['market_data_as_of']}。"]
        if quotes:
            lines.append("主要市场：" + "；".join(f"{item['symbol']} ${item['price']:,.2f}" for item in quotes[:5]) + "。")
        if trending:
            lines.extend(["", "今日全网热议", "；".join(f"{item['symbol']}（24小时 {item['mentions']} 次提及）" for item in trending) + "。"])
        if earnings:
            lines.extend(["", "美股财报（未来一周）", "；".join(earnings) + "。"])
        lines.extend(["", "组合事实"])
        if portfolio["connected"]:
            lines.append(f"组合净值：${portfolio['total_nav']:,.2f}；当日变化：${portfolio['daily_change']:,.2f}。")
            lines.append("主要持仓：" + "；".join(f"{item['symbol']} {item['weight']:.1%}" for item in holdings[:5]) + "。")
            lines.append(f"集中度 HHI：{portfolio['concentration_hhi']:.3f}。")
        else:
            lines.append("尚未连接真实组合账户，本期仅提供市场简报，不展示估算持仓或 NAV。")
        lines.extend(["", "模型推断与观察条件", "重点观察主要持仓相关事件、波动与集中度变化；若数据过期或持仓同步失败，应暂停使用本期判断。"])
        if context["market_stale"] or portfolio["stale"] or portfolio["missing_data"]:
            lines.append("数据提示：" + "；".join((["市场情报已过期"] if context["market_stale"] else []) + (["组合数据已过期"] if portfolio["stale"] else []) + portfolio["missing_data"]) + "。")
    else:
        lines = ["PureGamma Daily Crypto Brief | Portfolio", "", "Market facts", f"Market regime: {context['market_regime']}. Data as of {context['market_data_as_of']}."]
        if quotes:
            lines.append("Key markets: " + "; ".join(f"{item['symbol']} ${item['price']:,.2f}" for item in quotes[:5]) + ".")
        if trending:
            lines.extend(["", "Trending today", "; ".join(f"{item['symbol']} ({item['mentions']} mentions in 24h)" for item in trending) + "."])
        if earnings:
            lines.extend(["", "US earnings this week", "; ".join(earnings) + "."])
        lines.extend(["", "Portfolio facts"])
        if portfolio["connected"]:
            lines.append(f"NAV: ${portfolio['total_nav']:,.2f}; daily change: ${portfolio['daily_change']:,.2f}.")
            lines.append("Top holdings: " + "; ".join(f"{item['symbol']} {item['weight']:.1%}" for item in holdings[:5]) + ".")
            lines.append(f"Concentration HHI: {portfolio['concentration_hhi']:.3f}.")
        else:
            lines.append("No real portfolio account is connected. This is a market brief only; no estimated holdings or NAV are shown.")
        lines.extend(["", "Inference and watch conditions", "Monitor events, volatility, and concentration changes tied to major holdings. Invalidate this review if market or portfolio data becomes stale or synchronization fails."])
        warnings = (["Market intelligence is stale"] if context["market_stale"] else []) + (["Portfolio data is stale"] if portfolio["stale"] else []) + portfolio["missing_data"]
        if warnings:
            lines.append("Data notes: " + "; ".join(warnings) + ".")
    return "\n".join(lines).rstrip() + f"\n\n{disclaimer}"
