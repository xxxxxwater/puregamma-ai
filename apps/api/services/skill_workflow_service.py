"""Single invocation path for declarative workflow Skills (P0-6).

Every caller — the /api/skills/{slug}/run endpoint, Autopilot scheduled jobs,
and future module hooks — goes through :func:`invoke_workflow_skill`:

resolve (plan / rate / cost enforcement) → record_runs (reserved) → running →
run_workflow (the deterministic engine) → terminal state with output_summary,
evidence and usage recorded on the SkillRun.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from apps.api.services.skill_service import skill_registry
from packages.database.models import SkillRun, User
from packages.database.session import SessionLocal
from packages.skills.manifest import validate_json_instance
from packages.skills.registry import SkillResolutionError, update_skill_runs
from packages.skills.workflows import WorkflowError, load_workflow_definition, run_workflow

TERMINAL_RUN_STATUSES = {"completed", "failed", "canceled", "interrupted", "rejected"}


def _load_workflow(resolved) -> dict[str, Any]:
    try:
        return load_workflow_definition(resolved.version.content_bundle_json, resolved.manifest.workflow_template_ref)
    except WorkflowError as exc:
        status = 404 if exc.code == "SKILL_WORKFLOW_NOT_FOUND" else 422
        raise SkillResolutionError(exc.code, str(exc), status_code=status) from exc


def invoke_workflow_skill(
    db: Session,
    *,
    user: User,
    slug: str,
    inputs: dict[str, Any] | None,
    trigger_source: str,
    agent_run_id: str | None = None,
    estimated_credits: int | None = None,
    invocation_id: str | None = None,
    allow_autopilot: bool = False,
) -> SkillRun:
    """Resolve and execute one workflow Skill, returning its audited SkillRun."""
    payload = dict(inputs or {})
    registry = skill_registry(db, user)
    resolved = registry.resolve_many(
        [{"slug": slug}],
        trigger_source=trigger_source,
        allow_autopilot=allow_autopilot,
    )[0]
    manifest = resolved.manifest
    try:
        validate_json_instance(manifest.input_schema, payload, "input")
    except ValueError as exc:
        raise SkillResolutionError("SKILL_INPUT_INVALID", f"{slug}: {exc}", status_code=422) from exc
    workflow_def = _load_workflow(resolved)
    estimated = int(estimated_credits) if estimated_credits is not None else manifest.runtime.max_credits_per_run
    estimated = max(0, min(estimated, manifest.runtime.max_credits_per_run))
    registry.assert_cost([resolved], estimated)
    reference = invocation_id or f"skill-workflow:{uuid.uuid4()}"
    idempotency_key = f"skill-run:{agent_run_id or reference}:{resolved.skill.id}:{resolved.version.version}"
    existing = db.query(SkillRun).filter_by(idempotency_key=idempotency_key).one_or_none()
    if existing and existing.status in TERMINAL_RUN_STATUSES:
        return existing
    run = registry.record_runs(
        [resolved],
        agent_run_id=agent_run_id,
        external_run_id=reference,
        trace_id=reference,
        trigger_source=trigger_source,
        input_summary={
            "slug": slug,
            "inputs_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest(),
        },
        credits_reserved=estimated,
    )[0]
    db.commit()
    # Updates always target this invocation's own run via its external
    # reference, never sibling runs recorded under the same agent_run_id.
    update_kwargs = {"external_run_id": reference}
    update_skill_runs(db, status="running", **update_kwargs)
    db.commit()
    try:
        result = run_workflow(db, user=user, manifest=manifest, workflow_def=workflow_def, inputs=payload, skill_run=run)
    except Exception as exc:
        update_skill_runs(
            db,
            status="failed",
            credits_used=0,
            error_code=getattr(exc, "code", None) or "SKILL_WORKFLOW_ERROR",
            error_message=str(exc)[:500],
            **update_kwargs,
        )
        db.commit()
        raise
    try:
        validate_json_instance(manifest.output_schema, result.output, "output")
    except ValueError as exc:
        result.status = "failed"
        result.error = {"code": "SKILL_OUTPUT_INVALID", "message": str(exc)}
        result.output = {}
    terminal = "completed" if result.status in {"completed", "degraded"} else "failed"
    summary = f"{slug} {result.status}: {result.usage['steps_ok']}/{result.usage['steps_total']} steps ok"
    if result.degraded_steps:
        summary += f", degraded: {', '.join(result.degraded_steps)}"
    update_skill_runs(
        db,
        status=terminal,
        credits_used=estimated if terminal == "completed" else 0,
        output_summary=summary,
        evidence={"workflow": result.evidence_payload()},
        usage=result.usage,
        error_code=result.error.get("code") if result.error else None,
        error_message=result.error.get("message") if result.error else None,
        **update_kwargs,
    )
    db.commit()
    db.refresh(run)
    return run


def run_scheduled_workflow(slug: str, user_id: str, inputs: dict[str, Any] | None = None, *, invocation_id: str | None = None) -> dict:
    """Module-level convenience wrapper for Celery tasks."""
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user:
            return {"slug": slug, "status": "missing_user"}
        run = invoke_workflow_skill(
            db,
            user=user,
            slug=slug,
            inputs=inputs or {},
            trigger_source="scheduled_job",
            allow_autopilot=True,
            invocation_id=invocation_id,
        )
        return {"slug": slug, "run_id": run.id, "status": run.status}
    finally:
        db.close()
