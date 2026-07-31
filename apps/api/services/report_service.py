from __future__ import annotations

from datetime import date, datetime, timezone
import re
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.services.cost_control_service import assert_daily_report_limit, cached_daily_report
from apps.api.services.credit_service import quote_task, refund_task, reserve_task, settle_task
from apps.api.services.daily_brief_service import generate_daily_brief
from apps.api.services.daily_report_renderers import LLM_REPORT_TYPES, REPORT_TYPES, render_daily_report
from apps.api.services.entitlement_service import assert_action_allowed
from apps.api.services.market_intelligence_service import latest_or_create_intelligence
from apps.api.services.portfolio_service import portfolio_context
from packages.database.models import CreditReservationRecord, LLMCallLog, Report
from packages.reports.event_report import render_event_report
from packages.reports.playbook_report import render_playbook_report
from packages.strategies.registry import generate_playbooks


def create_daily_report(
    db: Session,
    user_id: str,
    language: str = "en",
    *,
    automation_key: str | None = None,
) -> Report:
    report_date = datetime.now(timezone.utc).date()
    idempotency_key = f"daily-report:{user_id}:{language}:{report_date.isoformat()}"
    if db.bind and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(73002002)"))
    cached = db.query(Report).filter_by(idempotency_key=idempotency_key).one_or_none() or cached_daily_report(db, user_id, language)
    if cached:
        return cached
    assert_daily_report_limit(db, user_id)
    assert_action_allowed(db, user_id, "daily_market_report")
    billing_task = "portfolio_daily_brief" if portfolio_context(db, user_id).get("connected") else "daily_market_report"
    quote = quote_task(task_type=billing_task, requested_model="default")
    reservation = reserve_task(
        db,
        user_id,
        quote,
        f"report-charge:{idempotency_key}",
        {"report_date": report_date.isoformat(), **({"automation_key": automation_key} if automation_key else {})},
    )
    # Make the reservation durable before provider execution, then serialize
    # concurrent generation for the same daily report on that reservation row.
    db.commit()
    db.query(CreditReservationRecord).filter_by(
        user_id=user_id,
        idempotency_key=reservation.idempotency_key,
    ).with_for_update().one()
    cached = db.query(Report).filter_by(idempotency_key=idempotency_key).one_or_none()
    if cached:
        return cached
    generation_started_at = datetime.now(timezone.utc)
    try:
        content = generate_daily_brief(db, user_id, language)
    except Exception:
        refund_task(db, user_id, reservation, "REPORT_GENERATION_FAILED", metadata={"report_date": report_date.isoformat()})
        db.commit()
        raise
    intelligence = latest_or_create_intelligence(db)
    report = Report(
        user_id=user_id,
        title="PureGamma 每日简报" if language == "zh" else "PureGamma Daily Brief",
        report_type="daily_market_report",
        language=language,
        content_markdown=content,
        assets=intelligence.assets,
        source_intelligence_id=intelligence.id,
        report_date=report_date,
        status="completed",
        idempotency_key=idempotency_key,
    )
    db.add(report)
    usage = (
        db.query(LLMCallLog)
        .filter(
            LLMCallLog.user_id == user_id,
            LLMCallLog.task_type == "daily_market_report",
            LLMCallLog.status == "success",
            LLMCallLog.created_at >= generation_started_at,
        )
        .order_by(LLMCallLog.created_at.desc())
        .first()
    )
    actual_quote = quote_task(
        task_type=billing_task,
        requested_model="default",
        resolved_model=usage.model if usage else "default",
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )
    settle_task(db, user_id, reservation, actual_quote.credits, metadata={"report_id": report.id, "usage_log_id": usage.id if usage else None})
    db.commit()
    db.refresh(report)
    return report


def create_typed_daily_report(
    db: Session,
    user_id: str,
    report_type: str,
    language: str = "en",
    *,
    local_date: date,
    scheduled: bool = False,
    automation_key: str | None = None,
) -> Report:
    """Generate-once-per-user-per-local-day for one typed daily report.

    Generalized form of :func:`create_daily_report` keyed by
    ``daily-report:{user}:{lang}:{report_type}:{local_date}`` (LOCAL date in the
    preference timezone, supplied by the caller).

    ``scheduled=True`` is used by the unified daily orchestrator: it SKIPS
    ``assert_daily_report_limit`` so scheduled dispatch never consumes the
    manual daily-report allowance, but it KEEPS the entitlement check and the
    credit reserve/settle/refund flow for the LLM-backed renderer
    (``crypto_daily`` → ``daily_market_report`` / ``portfolio_daily_brief``
    billing, same as today). Deterministic renderers (``us_daily``,
    ``week_ahead_events``, ``portfolio_daily``) never reserve credits.
    """
    if report_type not in REPORT_TYPES:
        raise ValueError(f"UNSUPPORTED_REPORT_TYPE:{report_type}")
    report_date = local_date
    idempotency_key = f"daily-report:{user_id}:{language}:{report_type}:{report_date.isoformat()}"
    if db.bind and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(73002002)"))
    cached = db.query(Report).filter_by(idempotency_key=idempotency_key).one_or_none()
    if cached:
        return cached
    if not scheduled:
        assert_daily_report_limit(db, user_id)
    assert_action_allowed(db, user_id, "daily_market_report")
    reservation = None
    quote = None
    billing_task = None
    if report_type in LLM_REPORT_TYPES:
        billing_task = "portfolio_daily_brief" if portfolio_context(db, user_id).get("connected") else "daily_market_report"
        quote = quote_task(task_type=billing_task, requested_model="default")
        reservation = reserve_task(
            db,
            user_id,
            quote,
            f"report-charge:{idempotency_key}",
            {"report_date": report_date.isoformat(), **({"automation_key": automation_key} if automation_key else {})},
        )
        # Make the reservation durable before provider execution, then serialize
        # concurrent generation for the same daily report on that reservation row.
        db.commit()
        db.query(CreditReservationRecord).filter_by(
            user_id=user_id,
            idempotency_key=reservation.idempotency_key,
        ).with_for_update().one()
        cached = db.query(Report).filter_by(idempotency_key=idempotency_key).one_or_none()
        if cached:
            return cached
    generation_started_at = datetime.now(timezone.utc)
    try:
        rendered = render_daily_report(db, user_id, report_type, language, local_date)
    except Exception:
        if reservation is not None:
            refund_task(db, user_id, reservation, "REPORT_GENERATION_FAILED", metadata={"report_date": report_date.isoformat()})
            db.commit()
        raise
    report = Report(
        user_id=user_id,
        title=rendered["title"],
        report_type=report_type,
        language=language,
        content_markdown=rendered["content_markdown"],
        assets=rendered.get("assets") or [],
        source_intelligence_id=rendered.get("source_intelligence_id"),
        report_date=report_date,
        status="completed",
        idempotency_key=idempotency_key,
    )
    db.add(report)
    if reservation is not None:
        usage = (
            db.query(LLMCallLog)
            .filter(
                LLMCallLog.user_id == user_id,
                LLMCallLog.task_type == "daily_market_report",
                LLMCallLog.status == "success",
                LLMCallLog.created_at >= generation_started_at,
            )
            .order_by(LLMCallLog.created_at.desc())
            .first()
        )
        actual_quote = quote_task(
            task_type=billing_task,
            requested_model="default",
            resolved_model=usage.model if usage else "default",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )
        settle_task(db, user_id, reservation, actual_quote.credits, metadata={"report_id": report.id, "usage_log_id": usage.id if usage else None})
    db.commit()
    db.refresh(report)
    return report


def create_event_report(db: Session, user_id: str, asset: str, event: str, language: str = "en") -> Report:
    quote = quote_task(task_type="event_report", requested_model="default")
    reservation = reserve_task(db, user_id, quote, f"event-report-charge:{user_id}:{uuid.uuid4()}")
    db.commit()
    try:
        content = render_event_report(asset, event, language)
        report = Report(
            user_id=user_id,
            title=f"PureGamma 事件报告：{asset}" if language == "zh" else f"PureGamma Event Report: {asset}",
            report_type="event_report",
            language=language,
            content_markdown=content,
            assets=[asset],
        )
        db.add(report)
        settle_task(db, user_id, reservation, quote.credits, metadata={"report_id": report.id})
        db.commit()
    except Exception:
        db.rollback()
        refund_task(db, user_id, reservation, "EVENT_REPORT_FAILED", metadata={"asset": asset})
        db.commit()
        raise
    db.refresh(report)
    return report


def create_playbook_report(db: Session, user_id: str, language: str = "en") -> Report:
    assert_action_allowed(db, user_id, "playbook_generation")
    quote = quote_task(task_type="playbook_generation", requested_model="default")
    reservation = reserve_task(db, user_id, quote, f"playbook-report-charge:{user_id}:{uuid.uuid4()}")
    db.commit()
    generation_started_at = datetime.now(timezone.utc)
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
        disclaimer = "使用该服务用户自行承担风险 提供本服务的主体概不负责AI生成所有责任。" if language == "zh" else "Users bear all risks of using this service. The service provider is not responsible for any AI-generated content."
        if generated.lstrip().startswith("#"):
            content = generated if disclaimer in generated else f"{generated.rstrip()}\n\n{disclaimer}"
    except Exception as exc:
        if get_settings().app_environment.lower() == "production":
            refund_task(db, user_id, reservation, "PLAYBOOK_MODEL_FAILED")
            db.commit()
            raise RuntimeError("PLAYBOOK_MODEL_UNAVAILABLE") from exc
    report = Report(
        user_id=user_id,
        title="PureGamma 策略框架" if language == "zh" else "PureGamma Strategy Playbooks",
        report_type="playbook",
        language=language,
        content_markdown=content,
        assets=[item["asset"] for item in playbooks],
    )
    db.add(report)
    usage = (
        db.query(LLMCallLog)
        .filter(
            LLMCallLog.user_id == user_id,
            LLMCallLog.task_type == "deepseek_playbook_generation",
            LLMCallLog.status == "success",
            LLMCallLog.created_at >= generation_started_at,
        )
        .order_by(LLMCallLog.created_at.desc())
        .first()
    )
    actual_quote = quote_task(
        task_type="playbook_generation",
        requested_model="default",
        resolved_model=usage.model if usage else "default",
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )
    settle_task(db, user_id, reservation, actual_quote.credits, metadata={"report_id": report.id, "usage_log_id": usage.id if usage else None})
    db.commit()
    db.refresh(report)
    return report


_REPORT_DISCLAIMERS = (
    "Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.",
    "使用该服务用户自行承担风险 提供本服务的主体概不负责AI生成所有责任。",
)


def _display_content(report: Report) -> str:
    content = report.content_markdown
    if report.report_type != "daily_market_report":
        return content
    for disclaimer in _REPORT_DISCLAIMERS:
        content = content.replace(disclaimer, "")
    content = re.sub(
        r"Users bear all risks of using this service\.\s*The service provider is not responsible for any AI[^A-Za-z0-9\n]{0,3}generated content\.",
        "",
        content,
        flags=re.IGNORECASE,
    )
    content = re.sub(r"使用该服务用户自行承担风险[^\n]*AI生成[^\n]*责任[。.]?", "", content)
    return re.sub(r"\n{3,}", "\n\n", content).strip()


def serialize_report(report: Report) -> dict:
    return {
        "id": report.id,
        "user_id": report.user_id,
        "title": report.title,
        "report_type": report.report_type,
        "language": report.language,
        "content_markdown": _display_content(report),
        "assets": report.assets,
        "source_intelligence_id": report.source_intelligence_id,
        "report_date": report.report_date.isoformat() if report.report_date else None,
        "status": report.status,
        "error_message": report.error_message,
        "created_at": report.created_at.isoformat(),
    }
