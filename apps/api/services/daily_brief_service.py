from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.services.market_intelligence_service import latest_or_create_intelligence
from apps.api.services.portfolio_service import portfolio_context
from packages.agents.llm.provider_factory import get_llm_provider
from packages.database.models import AgentConversation, AgentMessage, MarketSnapshot, UserPreference
from packages.reports.templates import disclaimer_for


def _recent_conversation_topics(db: Session, user_id: str) -> list[str]:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    conversations = db.query(AgentConversation).filter(AgentConversation.user_id == user_id, AgentConversation.status == "active", AgentConversation.updated_at >= since).order_by(AgentConversation.updated_at.desc()).limit(5).all()
    topics: list[str] = []
    for conversation in conversations:
        messages = db.query(AgentMessage).filter(AgentMessage.conversation_id == conversation.id, AgentMessage.role == "user", AgentMessage.status == "completed").order_by(AgentMessage.created_at.desc()).limit(3).all()
        topics.extend(message.content[:120].replace("\n", " ") for message in messages if message.content.strip())
    return topics[:8]


def gather_context(db: Session, user_id: str, language: str) -> dict:
    intelligence = latest_or_create_intelligence(db)
    snapshots = db.query(MarketSnapshot).filter(MarketSnapshot.id.in_(intelligence.source_snapshot_ids or [])).all()
    preference = db.query(UserPreference).filter_by(user_id=user_id).one_or_none()
    portfolio = portfolio_context(db, user_id)
    return {
        "language": language,
        "shared_intelligence_id": intelligence.id,
        "market_regime": intelligence.market_regime,
        "market_summary": intelligence.summary_markdown,
        "market_data_as_of": max((row.timestamp for row in snapshots), default=intelligence.created_at).astimezone(timezone.utc).isoformat(),
        "market_stale": datetime.now(timezone.utc) - intelligence.created_at.astimezone(timezone.utc) > timedelta(hours=8),
        "quotes": [{"symbol": row.asset_id, "price": row.price, "funding_rate": row.funding_rate, "open_interest": row.open_interest, "source_timestamp": row.timestamp.astimezone(timezone.utc).isoformat()} for row in snapshots],
        "portfolio": portfolio,
        "portfolio_shared_with_llm": bool(preference.include_portfolio_in_ai) if preference else True,
        "recent_topics": _recent_conversation_topics(db, user_id),
    }


def generate_daily_brief(db: Session, user_id: str, language: str) -> str:
    context = gather_context(db, user_id, language)
    disclaimer = disclaimer_for(language)
    if not context["portfolio_shared_with_llm"]:
        return _local_brief(context, language, disclaimer)
    prompt = (
        "Write a concise portfolio-first daily research brief in Chinese. " if language == "zh" else "Write a concise portfolio-first daily research brief in English. "
    ) + "Distinguish market facts, portfolio facts, and inference. Include portfolio relevance, concentration risk, watch conditions, invalidation conditions, source timestamps, stale or missing-data warnings. Never invent values. No trade execution advice.\n\n" + json.dumps(context, ensure_ascii=False, default=str)
    try:
        generated = get_llm_provider().complete(prompt, task_type="daily_market_report", locale=language, user_id=user_id, db=db)
    except Exception:
        return _local_brief(context, language, disclaimer)
    title = "PureGamma 组合每日简报" if language == "zh" else "PureGamma Daily Crypto Brief | Portfolio"
    if title not in generated:
        generated = f"{title}\n\n{generated.lstrip()}"
    if disclaimer not in generated:
        generated = f"{generated.rstrip()}\n\n{disclaimer}"
    return generated


def _local_brief(context: dict, language: str, disclaimer: str) -> str:
    portfolio = context["portfolio"]
    quotes = context["quotes"]
    holdings = portfolio["top_holdings"]
    if language == "zh":
        lines = ["PureGamma 组合每日简报", "", "市场事实", f"市场状态：{context['market_regime']}。数据时间：{context['market_data_as_of']}。"]
        if quotes:
            lines.append("主要市场：" + "；".join(f"{item['symbol']} ${item['price']:,.2f}" for item in quotes[:5]) + "。")
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
