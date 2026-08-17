"""Server-side service for the Harness deep-research HTTP contract.

Implements docs/mobile/MOBILE_API_CONTRACT.md §2 on top of the existing
``harness_research_runs`` / ``evidence_snapshots`` / ``research_artifacts``
tables and the audited Harness state machine.

Execution model (honest, in-worker):
  queued -> preparing (freeze real market evidence from the research event
  pipeline) -> running (one gateway chat call) -> validating (citation check)
  -> completed | degraded | failed | canceled | timed_out.

The isolated runner image remains the Phase-2 hardening target; this service
never executes user code and only calls audited gateway/data services.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from apps.api.config import get_settings
from packages.database.models import (
    EvidenceSnapshot,
    HarnessResearchRun,
    HarnessRunStateTransition,
    MarketEvent,
    ResearchArtifact,
    User,
    new_id,
    utcnow,
)
from packages.harness.adapter import artifact_content_hash
from packages.harness.composition import MINIMAL_CORDIS_COMPOSITION
from packages.harness.state_machine import TERMINAL_STATES, transition_run
from packages.harness.versions import PINNED_HARNESS_VERSIONS, compute_input_hash

HARNESS_SKILL_ALLOWLIST: frozenset[str] = frozenset({"harness_deep_research"})
HARNESS_DATA_SOURCES: frozenset[str] = frozenset({"market", "news", "options", "earnings"})
RETRYABLE_STATUSES: frozenset[str] = frozenset({"failed", "canceled", "timed_out"})

MAX_EVIDENCE_ITEMS = 12
MAX_EVIDENCE_EXCERPT = 300
MAX_GOAL_CHARS = 4000
MAX_ARTIFACT_TOKENS = 1200


class HarnessDisabledError(RuntimeError):
    pass


class HarnessQuotaError(RuntimeError):
    pass


class HarnessStateConflict(RuntimeError):
    pass


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _aware(value: Any) -> Any:
    """Normalize sqlite naive datetimes to UTC-aware for comparisons."""
    if value is None or not hasattr(value, "tzinfo"):
        return value
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _run_name(row: HarnessResearchRun) -> str:
    goal = (row.requested_goal_summary or "").strip()
    if not goal:
        return row.id
    first_line = goal.splitlines()[0].strip()
    return first_line[:80] or row.id


def _verification_for(row: HarnessResearchRun) -> str | None:
    return {
        "completed": "verified",
        "degraded": "degraded",
        "failed": "failed",
        "canceled": "incomplete",
        "timed_out": "incomplete",
    }.get(row.status)


def serialize_harness_run(row: HarnessResearchRun, *, evidence_count: int = 0, citation_count: int = 0) -> dict[str, Any]:
    usage = row.usage_json or {}
    evidence_ids = usage.get("evidence_ids") or []
    citations = usage.get("citations") or []
    return {
        "id": row.id,
        "name": _run_name(row),
        "status": row.status,
        "verification": _verification_for(row),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        "credits_used": usage.get("credits_used"),
        "credits_estimate": usage.get("credits_estimate"),
        "data_sources": usage.get("data_sources") or [],
        "evidence_count": int(usage.get("evidence_count") or evidence_count or len(evidence_ids)),
        "citation_count": int(usage.get("citation_count") or citation_count or len(citations)),
        "is_degraded": bool(row.status == "degraded"),
        "error_message": row.error_summary,
        "summary": usage.get("summary"),
        "disclaimer": "研究结论未经人工验证，仅供研究参考，不构成事实断言或投资建议。",
    }


def create_harness_run(
    db: Session,
    user_id: str,
    *,
    name: str,
    prompt: str,
    data_sources: list[str],
    skill: str,
) -> tuple[HarnessResearchRun, bool]:
    """Create (or idempotently return) a harness run. Returns (row, created)."""
    settings = get_settings()
    user = db.get(User, user_id)
    if user is None:
        raise LookupError("user not found")
    if not settings.harness_research_enabled:
        raise HarnessDisabledError("Harness Research is disabled")
    if settings.harness_research_admin_only and user.role != "admin":
        raise HarnessDisabledError("Harness Research is admin-only")
    if skill not in HARNESS_SKILL_ALLOWLIST:
        raise ValueError(f"skill not allowed: {skill}")
    unknown_sources = set(data_sources) - HARNESS_DATA_SOURCES
    if unknown_sources:
        raise ValueError(f"unknown data_sources: {', '.join(sorted(unknown_sources))}")

    name = (name or "").strip()[:120] or "Research"
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("prompt is required")

    goal = f"{name}\n{prompt}"[:MAX_GOAL_CHARS]
    input_hash = compute_input_hash(goal)
    idempotency_key = f"harness:{user_id}:{input_hash}"
    existing = (
        db.query(HarnessResearchRun)
        .filter(HarnessResearchRun.idempotency_key == idempotency_key)
        .one_or_none()
    )
    if existing is not None:
        if existing.status == "queued":
            queue_harness_run(db, existing.id)
        return existing, False

    from sqlalchemy import func

    today = utcnow().date()
    runs_today = (
        db.query(HarnessResearchRun)
        .filter(
            HarnessResearchRun.user_id == user_id,
            func.date(HarnessResearchRun.created_at) == today,
        )
        .count()
    )
    if runs_today >= settings.harness_max_runs_per_user_per_day:
        raise HarnessQuotaError(
            f"daily harness run limit reached ({settings.harness_max_runs_per_user_per_day})"
        )

    from apps.api.services.credit_service import quote_task, reserve_task

    quote = quote_task(
        task_type="research_run",
        requested_model="deepseek-v4-flash",
        resolved_model="deepseek-v4-flash",
        input_tokens=max(1, len(prompt) // 4),
        output_tokens=MAX_ARTIFACT_TOKENS,
        tool_calls=["get_market_series", "get_options_context"],
        selected_data_sources=data_sources,
    )

    run_id = new_id()
    row = HarnessResearchRun(
        id=run_id,
        user_id=user_id,
        status="queued",
        requested_goal_summary=goal,
        input_hash=input_hash,
        harness_version=PINNED_HARNESS_VERSIONS.sdk_version,
        runtime_version=PINNED_HARNESS_VERSIONS.runtime_bin_version,
        cordis_config_hash=MINIMAL_CORDIS_COMPOSITION.config_hash(),
        plugin_lock_hash=PINNED_HARNESS_VERSIONS.plugin_lock_hash,
        provider="deepseek",
        model="deepseek-v4-flash",
        max_budget_credits=settings.harness_run_max_budget_credits,
        credits_reserved=int(quote.credits),
        timeout_at=utcnow() + timedelta(seconds=settings.harness_run_timeout_seconds),
        usage_json={
            "data_sources": data_sources,
            "skill": skill,
            "reservation_key": f"harness-run:{run_id}",
            "credits_estimate": quote.credits,
        },
        idempotency_key=idempotency_key,
        trace_id=run_id,
    )
    reservation = reserve_task(
        db,
        user_id,
        quote,
        f"harness-run:{run_id}",
        metadata={"harness_run_id": run_id},
    )
    row.credits_reserved = int(reservation.credits)
    row.usage_json = {**row.usage_json, "credits_estimate": reservation.credits}
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, True


def queue_harness_run(db: Session, run_id: str) -> str:
    """Hand a queued harness run to the worker; inline only outside production."""
    try:
        from apps.api.redis_client import get_redis
        get_redis().ping()
        from packages.workers.tasks import execute_harness_research_run
        execute_harness_research_run.delay(run_id)
        return "celery"
    except Exception as exc:
        settings = get_settings()
        if settings.app_environment.lower() == "production":
            row = db.get(HarnessResearchRun, run_id)
            if row and row.status == "queued":
                try:
                    transition_run(db, row, "failed", reason=f"queue unavailable: {str(exc)[:200]}", actor="orchestrator")
                    _refund_run(db, row, "HARNESS_QUEUE_UNAVAILABLE")
                except Exception:
                    pass
                db.commit()
            raise RuntimeError("Harness queue is temporarily unavailable") from exc
        from packages.workers.tasks import execute_harness_research_run
        execute_harness_research_run(run_id)
        return "inline"


def list_harness_runs(
    db: Session, user_id: str, *, limit: int = 20, offset: int = 0
) -> tuple[list[HarnessResearchRun], int]:
    limit = max(1, min(100, limit))
    offset = max(0, offset)
    base = db.query(HarnessResearchRun).filter(HarnessResearchRun.user_id == user_id)
    total = base.count()
    rows = base.order_by(HarnessResearchRun.created_at.desc()).limit(limit).offset(offset).all()
    return rows, total


def cancel_harness_run(db: Session, user_id: str, run_id: str) -> HarnessResearchRun:
    row = (
        db.query(HarnessResearchRun)
        .filter(HarnessResearchRun.id == run_id, HarnessResearchRun.user_id == user_id)
        .one_or_none()
    )
    if row is None:
        raise LookupError("research run not found")
    if row.status == "canceled":
        return row
    if row.status in TERMINAL_STATES:
        raise HarnessStateConflict(f"cannot cancel a {row.status} research run")
    try:
        transition_run(db, row, "canceled", reason="canceled by user", actor="user")
    except Exception:
        db.rollback()
        fresh = db.get(HarnessResearchRun, run_id)
        if fresh is not None and fresh.status == "canceled":
            return fresh
        raise
    _refund_run(db, row, "HARNESS_RUN_CANCELED")
    db.commit()
    return row


def retry_harness_run(db: Session, user_id: str, run_id: str) -> HarnessResearchRun:
    row = (
        db.query(HarnessResearchRun)
        .filter(HarnessResearchRun.id == run_id, HarnessResearchRun.user_id == user_id)
        .one_or_none()
    )
    if row is None:
        raise LookupError("research run not found")
    if row.status not in RETRYABLE_STATUSES:
        raise HarnessStateConflict(f"cannot retry a {row.status} research run")

    settings = get_settings()
    goal = row.requested_goal_summary or ""
    parts = goal.split("\n", 1)
    name = parts[0][:120] or "Research"
    prompt = parts[1] if len(parts) > 1 else goal
    data_sources = (row.usage_json or {}).get("data_sources") or []
    skill = (row.usage_json or {}).get("skill") or "harness_deep_research"

    new_row, _ = create_harness_run(
        db,
        user_id,
        name=f"{name} (retry)",
        prompt=prompt,
        data_sources=data_sources,
        skill=skill,
    )
    if new_row.status == "queued":
        queue_harness_run(db, new_row.id)
    return new_row


def run_evidence(db: Session, run: HarnessResearchRun) -> list[dict[str, Any]]:
    if run.evidence_snapshot_id:
        snapshot = db.get(EvidenceSnapshot, run.evidence_snapshot_id)
        if snapshot is not None:
            items = (snapshot.normalized_evidence_json or {}).get("items") or []
            return [dict(item) for item in items]
    return []


def run_artifacts(db: Session, run: HarnessResearchRun) -> list[dict[str, Any]]:
    rows = (
        db.query(ResearchArtifact)
        .filter(ResearchArtifact.research_run_id == run.id)
        .order_by(ResearchArtifact.created_at.desc())
        .all()
    )
    output: list[dict[str, Any]] = []
    for artifact in rows:
        structured = artifact.structured_json or {}
        output.append(
            {
                "id": artifact.id,
                "type": structured.get("type") or "report",
                "title": structured.get("title") or "Research artifact",
                "url": None,
                "status": artifact.status,
                "markdown": artifact.markdown_rendering,
                "created_at": _iso(artifact.created_at),
            }
        )
    return output


def _refund_run(db: Session, row: HarnessResearchRun, reason: str) -> None:
    usage = row.usage_json or {}
    key = usage.get("reservation_key")
    if not key:
        return
    try:
        from apps.api.services.credit_service import CreditReservation, refund_task
        refund_task(
            db,
            row.user_id,
            CreditReservation(key, int(row.credits_reserved or 0)),
            reason,
            metadata={"harness_run_id": row.id},
        )
        usage["credits_used"] = 0
        row.usage_json = usage
        flag_modified(row, "usage_json")
    except Exception:
        # A terminal reservation (already settled/refunded) is fine; never
        # let billing bookkeeping break the run lifecycle.
        pass


def _settle_run(db: Session, row: HarnessResearchRun, actual: int) -> None:
    usage = row.usage_json or {}
    key = usage.get("reservation_key")
    if not key:
        return
    try:
        from apps.api.services.credit_service import CreditReservation, settle_task
        settlement = settle_task(
            db,
            row.user_id,
            CreditReservation(key, int(row.credits_reserved or 0)),
            max(1, min(int(row.credits_reserved or 0), actual)),
            metadata={"harness_run_id": row.id},
        )
        usage["credits_used"] = settlement.actual
        row.usage_json = usage
        flag_modified(row, "usage_json")
    except Exception:
        # Never let billing bookkeeping break the run lifecycle.
        pass


def _gather_evidence(db: Session, row: HarnessResearchRun) -> list[dict[str, Any]]:
    """Freeze real market research events as the run's evidence bundle."""
    from apps.api.services.research_event_service import build_research_events

    snapshot = build_research_events(db, kind="harness", window_hours=24)
    events = (
        db.query(MarketEvent)
        .filter(MarketEvent.research_snapshot_id == snapshot.id, MarketEvent.status == "active")
        .order_by(MarketEvent.confidence.desc(), MarketEvent.collected_at.desc())
        .limit(MAX_EVIDENCE_ITEMS)
        .all()
    )
    items: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        items.append(
            {
                "id": event.id,
                "citation_index": index,
                "provider": event.source_provider or "puregamma",
                "title": event.title,
                "url": event.source_url,
                "source_scope": event.event_type or "market",
                "excerpt": (event.summary or "")[:MAX_EVIDENCE_EXCERPT],
                "is_verified": True,
                "verification_note": None,
                "fetched_at": _iso(event.collected_at),
            }
        )
    return items


def _execute_run(db: Session, run: HarnessResearchRun) -> dict[str, Any]:
    """Worker-side execution: preparing -> running -> validating -> terminal."""
    settings = get_settings()
    if run.status != "queued":
        return serialize_harness_run(run)

    deadline = _aware(run.timeout_at)
    if deadline is not None and utcnow() > deadline:
        transition_run(db, run, "timed_out", reason="deadline passed before start", actor="orchestrator")
        _refund_run(db, run, "HARNESS_RUN_TIMED_OUT")
        db.commit()
        return serialize_harness_run(run)

    # preparing ---------------------------------------------------------
    transition_run(db, run, "preparing", reason="orchestrator accepted run", actor="orchestrator")
    db.commit()
    try:
        evidence_items = _gather_evidence(db, run)
    except Exception as exc:
        transition_run(db, run, "failed", reason=f"evidence pipeline failed: {str(exc)[:200]}", actor="orchestrator")
        _refund_run(db, run, "HARNESS_EVIDENCE_FAILED")
        db.commit()
        return serialize_harness_run(run)

    evidence_payload = json.dumps({"items": evidence_items}, ensure_ascii=True, sort_keys=True)
    evidence_hash = hashlib.sha256(evidence_payload.encode("utf-8")).hexdigest()
    snapshot = EvidenceSnapshot(
        user_id=run.user_id,
        schema_version="1.0",
        source_scope="run",
        freshness_window_seconds=900,
        content_hash=evidence_hash,
        normalized_evidence_json={"items": evidence_items},
        source_ids_json=[item["id"] for item in evidence_items],
        provider_list_json=[item["provider"] for item in evidence_items],
        source_timestamps_json=[],
        fetched_timestamps_json=[item["fetched_at"] for item in evidence_items],
        mock_fallback_flags_json=[False for _ in evidence_items],
        authorization_context_json={"harness_run_id": run.id},
    )
    db.add(snapshot)
    db.flush()
    run.evidence_snapshot_id = snapshot.id
    run.evidence_snapshot_hash = evidence_hash
    usage = dict(run.usage_json or {})
    usage["evidence_count"] = len(evidence_items)
    usage["evidence_ids"] = [item["id"] for item in evidence_items]
    run.usage_json = usage
    db.commit()

    # running -----------------------------------------------------------
    transition_run(db, run, "running", reason="evidence frozen; invoking gateway", actor="orchestrator")
    db.commit()
    from packages.gateway.service import execute_chat

    system = (
        "You are PureGamma Harness, a deep-research analyst. Work ONLY from the "
        "provided evidence. Every claim must cite evidence by [n]. Never invent "
        "data, never give trading orders, never promise returns. End with "
        "limitations and a one-paragraph summary."
    )
    excerpts = "\n\n".join(
        f"[{item['citation_index']}] {item['title']} — {item['excerpt']}" for item in evidence_items
    )
    request = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Research goal:\n{run.requested_goal_summary}\n\nEvidence:\n{excerpts[:8000]}"},
        ],
        "max_tokens": MAX_ARTIFACT_TOKENS,
    }
    try:
        result, route = execute_chat(db, run.model, request)
        content = (result.content or "").strip()
        input_tokens = int((result.usage.input_tokens if result.usage else 0) or 0)
        output_tokens = int((result.usage.output_tokens if result.usage else 0) or 0)
    except Exception as exc:
        transition_run(db, run, "failed", reason=f"gateway call failed: {str(exc)[:200]}", actor="orchestrator")
        _refund_run(db, run, "HARNESS_GATEWAY_FAILED")
        db.commit()
        return serialize_harness_run(run)

    # validating --------------------------------------------------------
    transition_run(db, run, "validating", reason="citation verification", actor="orchestrator")
    db.commit()
    citations: list[dict[str, Any]] = []
    matched = 0
    for item in evidence_items:
        marker = f"[{item['citation_index']}]"
        if marker in content:
            matched += 1
            citations.append(
                {
                    "citation_index": item["citation_index"],
                    "title": item["title"],
                    "url": item["url"],
                    "source_scope": item["source_scope"],
                }
            )
    final_status = "completed" if (matched > 0 or not evidence_items) else "degraded"
    transition_run(
        db,
        run,
        final_status,
        reason=f"validation done: {matched}/{len(evidence_items)} citations matched",
        actor="orchestrator",
    )
    db.commit()

    # artifact + settlement ---------------------------------------------
    summary = content[:240]
    structured = {"type": "report", "title": _run_name(run), "summary": summary}
    artifact = ResearchArtifact(
        user_id=run.user_id,
        research_run_id=run.id,
        status="validated" if final_status == "completed" else "degraded",
        schema_version="1.0",
        structured_json=structured,
        markdown_rendering=content,
        citations_json=citations,
        methodology="Evidence-grounded gateway research with citation verification.",
        assumptions_json=[{"statement": "All facts derive from the frozen evidence bundle."}],
        limitations_json=[{"statement": "No out-of-evidence inference; conclusions unverified by humans."}],
        tool_run_summaries_json=[{"tool": "research_event_service", "stage": "evidence"}],
        artifact_file_refs_json=[],
        content_hash=artifact_content_hash(structured, content, citations),
        validation_result_json={
            "citations_matched": matched,
            "citations_total": len(evidence_items),
            "route_provider": getattr(route, "provider", None).id if getattr(route, "provider", None) else None,
        },
    )
    db.add(artifact)
    db.flush()
    run.artifact_id = artifact.id
    run.settlement_status = "settled"
    usage = dict(run.usage_json or {})
    usage["citations"] = citations
    usage["citation_count"] = len(citations)
    usage["summary"] = summary
    usage["input_tokens"] = input_tokens
    usage["output_tokens"] = output_tokens
    run.usage_json = usage
    from apps.api.services.credit_service import quote_task

    actual_quote = quote_task(
        task_type="research_run",
        requested_model="deepseek-v4-flash",
        resolved_model=run.model,
        input_tokens=max(1, input_tokens),
        output_tokens=max(1, output_tokens),
        tool_calls=["get_market_series"],
        selected_data_sources=usage.get("data_sources") or [],
    )
    _settle_run(db, run, actual_quote.credits)
    db.commit()
    return serialize_harness_run(run)


def execute_queued_run(db: Session, run_id: str) -> dict[str, Any]:
    run = db.get(HarnessResearchRun, run_id)
    if run is None:
        raise LookupError("research run not found")
    try:
        return _execute_run(db, run)
    except Exception as exc:
        db.rollback()
        run = db.get(HarnessResearchRun, run_id)
        if run is not None and run.status not in TERMINAL_STATES:
            transition_run(db, run, "failed", reason=f"orchestrator error: {str(exc)[:200]}", actor="orchestrator")
            _refund_run(db, run, "HARNESS_ORCHESTRATOR_ERROR")
            db.commit()
        return serialize_harness_run(run) if run is not None else {"id": run_id, "status": "failed"}
