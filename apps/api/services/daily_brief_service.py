from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.services.market_intelligence_service import latest_or_create_intelligence
from apps.api.services.signal_service import scan_signals, serialize_signal
from packages.agents.llm.provider_factory import get_llm_provider
from packages.agents.research_agent import ResearchAgent
from packages.database.models import AgentConversation, AgentMessage
from packages.reports.templates import disclaimer_for


def _recent_conversation_topics(db: Session, user_id: str, language: str) -> str:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    conversations = (
        db.query(AgentConversation)
        .filter(
            AgentConversation.user_id == user_id,
            AgentConversation.status == "active",
            AgentConversation.updated_at >= since,
        )
        .order_by(AgentConversation.updated_at.desc())
        .limit(5)
        .all()
    )
    if not conversations:
        return ""
    topics = []
    for conversation in conversations:
        user_messages = (
            db.query(AgentMessage)
            .filter(
                AgentMessage.conversation_id == conversation.id,
                AgentMessage.role == "user",
                AgentMessage.status == "completed",
            )
            .order_by(AgentMessage.created_at.desc())
            .limit(3)
            .all()
        )
        for msg in user_messages:
            snippet = msg.content[:120].replace("\n", " ")
            if snippet:
                topics.append(snippet)
    if not topics:
        return ""
    if language == "zh":
        return "用户近期关注话题: " + "; ".join(topics[:8])
    return "Recent user interests: " + "; ".join(topics[:8])


def _format_quote_line(quote, language: str) -> str:
    sym = quote.symbol
    price = f"${quote.price:,.2f}"
    if language == "zh":
        return f"{sym} {price} | 情绪 {quote.sentiment_score:.2f} | 资金费率 {quote.funding_rate:.3%}"
    return f"{sym} {price} | sentiment {quote.sentiment_score:.2f} | funding {quote.funding_rate:.3%}"


def gather_context(db: Session, user_id: str, language: str) -> str:
    intelligence = latest_or_create_intelligence(db)
    signals = [serialize_signal(s) for s in scan_signals(db, intelligence.assets)]
    research = ResearchAgent().research(intelligence.assets)

    lines = []
    if language == "zh":
        lines.append(f"市场状态: {research['market_regime']}")
        lines.append(f"风险概述: {research['risk_summary']}")
        lines.append("行情:")
    else:
        lines.append(f"Market regime: {research['market_regime']}")
        lines.append(f"Risk summary: {research['risk_summary']}")
        lines.append("Quotes:")
    for quote in research["quotes"]:
        lines.append(f"  {_format_quote_line(quote, language)}")

    if signals:
        label = "重点信号" if language == "zh" else "Key signals"
        lines.append(f"{label}:")
        for sig in signals[:5]:
            lines.append(f"  {sig['asset']} {sig['direction']}: {sig['thesis'][:100]}")

    topics = _recent_conversation_topics(db, user_id, language)
    if topics:
        lines.append(topics)

    context = "\n".join(lines)
    return context


def generate_daily_brief(db: Session, user_id: str, language: str) -> str:
    context = gather_context(db, user_id, language)
    disclaimer = disclaimer_for(language)

    if language == "zh":
        prompt = (
            f"用中文撰写一份200字以内的每日简报。直接输出内容，不要用 # 标题。\n\n"
            f"=== 数据上下文 ===\n{context}\n\n"
            f"=== 要求 ===\n"
            f"- 总字数严格控制在200字以内\n"
            f"- 以市场概况+关键信号+关联用户关注的结构组织\n"
            f"- 不要使用 markdown 的 # 或 ## 标题符号\n"
            f"- 语气专业直接"
        )
    else:
        prompt = (
            f"Write a concise daily brief under 200 words. Output directly, no # headings.\n\n"
            f"=== Context ===\n{context}\n\n"
            f"=== Requirements ===\n"
            f"- Strictly under 200 words\n"
            f"- Structure: market overview + key signals + user relevance\n"
            f"- No markdown # or ## headings\n"
            f"- Professional direct tone"
        )

    try:
        provider = get_llm_provider()
        generated = provider.complete(
            prompt,
            task_type="daily_market_report",
            locale=language,
            user_id=user_id,
            db=db,
        )
    except Exception:
        return _fallback_brief(context, language, disclaimer)

    if disclaimer not in generated:
        generated = f"{generated.rstrip()}\n\n{disclaimer}"
    word_count = len(generated.replace("\n", " ").split())
    if word_count > 300:
        lines_out = generated.strip().split("\n")
        trimmed = []
        total = 0
        for line in lines_out:
            words = len(line.split())
            if total + words > 250:
                break
            trimmed.append(line)
            total += words
        generated = "\n".join(trimmed).rstrip()
        if disclaimer not in generated:
            generated = f"{generated}\n\n{disclaimer}"
    return generated


def _fallback_brief(context: str, language: str, disclaimer: str) -> str:
    if language == "zh":
        header = "今日市场概况"
    else:
        header = "Today's market overview"
    lines = [header, ""]
    for line in context.split("\n")[:15]:
        if line.strip():
            lines.append(line.strip())
    brief = "\n".join(lines)
    word_count = len(brief.split())
    if word_count > 200:
        brief = "\n".join(lines[:10])
    return f"{brief.rstrip()}\n\n{disclaimer}"
