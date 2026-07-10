from __future__ import annotations

from sqlalchemy.orm import Session

from apps.api.services.cost_control_service import assert_daily_report_limit, cached_daily_report
from apps.api.services.credit_service import consume_credits
from apps.api.services.entitlement_service import assert_action_allowed
from apps.api.services.market_intelligence_service import latest_or_create_intelligence
from apps.api.services.signal_service import scan_signals, serialize_signal
from packages.agents.research_agent import ResearchAgent
from packages.agents.report_writer_agent import ReportWriterAgent
from packages.billing.credits import cost_for
from packages.database.models import Report
from packages.reports.event_report import render_event_report
from packages.reports.playbook_report import render_playbook_report
from packages.strategies.registry import generate_playbooks


def create_daily_report(db: Session, user_id: str, language: str = "en") -> Report:
    cached = cached_daily_report(db, user_id, language)
    if cached:
        return cached
    assert_daily_report_limit(db, user_id)
    assert_action_allowed(db, user_id, "daily_market_report")
    consume_credits(db, user_id, "daily_market_report", cost_for("daily_market_report"))
    intelligence = latest_or_create_intelligence(db)
    signals = [serialize_signal(signal) for signal in scan_signals(db, intelligence.assets)]
    research = ResearchAgent().research(intelligence.assets)
    content = ReportWriterAgent().daily(research, signals, language, user_id=user_id, db=db)
    report = Report(
        user_id=user_id,
        title="PureGamma 每日加密市场简报" if language == "zh" else "PureGamma Daily Crypto Brief",
        report_type="daily_market_report",
        language=language,
        content_markdown=content,
        assets=intelligence.assets,
        source_intelligence_id=intelligence.id,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def create_event_report(db: Session, user_id: str, asset: str, event: str, language: str = "en") -> Report:
    consume_credits(db, user_id, "event_report", cost_for("event_report"))
    report = Report(
        user_id=user_id,
        title=f"PureGamma 事件报告：{asset}" if language == "zh" else f"PureGamma Event Report: {asset}",
        report_type="event_report",
        language=language,
        content_markdown=render_event_report(asset, event, language),
        assets=[asset],
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def create_playbook_report(db: Session, user_id: str, language: str = "en") -> Report:
    assert_action_allowed(db, user_id, "playbook_generation")
    consume_credits(db, user_id, "playbook_generation", cost_for("playbook_generation"))
    playbooks = generate_playbooks()
    content = render_playbook_report(playbooks, language)
    try:
        from packages.agents.llm.provider_factory import get_llm_provider
        generated = get_llm_provider().complete(
            f"Generate a concise strategy playbook report in locale={language}. Keep disclaimer. Playbooks: {playbooks}",
            task_type="deepseek_playbook_generation",
            locale=language,
            user_id=user_id,
            db=db,
        )
        disclaimer = "本内容仅供信息和研究参考，不构成投资建议。" if language == "zh" else "This is not financial advice."
        if generated.lstrip().startswith("#"):
            content = generated if disclaimer in generated else f"{generated.rstrip()}\n\n{disclaimer}"
    except Exception:
        pass
    report = Report(
        user_id=user_id,
        title="PureGamma 策略框架" if language == "zh" else "PureGamma Strategy Playbooks",
        report_type="playbook",
        language=language,
        content_markdown=content,
        assets=[item["asset"] for item in playbooks],
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def serialize_report(report: Report) -> dict:
    return {
        "id": report.id,
        "user_id": report.user_id,
        "title": report.title,
        "report_type": report.report_type,
        "language": report.language,
        "content_markdown": report.content_markdown,
        "assets": report.assets,
        "source_intelligence_id": report.source_intelligence_id,
        "created_at": report.created_at.isoformat(),
    }
