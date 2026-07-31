from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.services.skill_service import serialize_installation, skill_registry
from apps.api.services.skill_workflow_service import invoke_workflow_skill
from packages.database.models import Skill, SkillInstallation, SkillRun, SkillSource, SkillVersion, User
from packages.skills.manifest import validate_github_source, validate_skill_bundle
from packages.skills.registry import SkillResolutionError


router = APIRouter(prefix="/skills", tags=["skills"])


class SkillImportRequest(BaseModel):
    source_type: Literal["upload", "github"] = "upload"
    repo_url: str | None = None
    commit_hash: str | None = None
    files: dict[str, str] = Field(min_length=1, max_length=100)


class SkillInstallRequest(BaseModel):
    pinned_version: str | None = Field(default=None, max_length=80)
    workspace_id: str | None = Field(default=None, max_length=80)
    config_overrides: dict[str, Any] = Field(default_factory=dict)


class SkillInvocationRequest(BaseModel):
    skill_refs: list[dict[str, Any]] = Field(default_factory=list, max_length=8)
    trigger_source: Literal["agent_chat", "dashboard", "report", "portfolio", "autopilot", "nautilus", "api", "scheduled_job"]
    allow_autopilot: bool = False
    allow_order_intent: bool = False
    estimated_credits: int = Field(default=0, ge=0, le=10_000)


def _raise_skill_error(exc: SkillResolutionError) -> None:
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc


@router.get("")
def catalog(
    include_disabled: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return {"skills": skill_registry(db, user).list_visible(include_disabled=include_disabled)}


@router.get("/installations")
def installations(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    rows = db.query(SkillInstallation).filter_by(user_id=user.id).order_by(SkillInstallation.created_at.desc()).all()
    return {"installations": [serialize_installation(row) for row in rows]}


@router.get("/runs")
def runs(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    rows = db.query(SkillRun).filter_by(user_id=user.id).order_by(SkillRun.started_at.desc()).limit(limit).all()
    return {"runs": [{
        "id": row.id,
        "skill_id": row.skill_id,
        "skill_version_id": row.skill_version_id,
        "installation_id": row.installation_id,
        "agent_run_id": row.agent_run_id,
        "trigger_source": row.trigger_source,
        "status": row.status,
        "input_summary": row.input_summary_json or {},
        "output_summary": row.output_summary,
        "evidence": row.evidence_json or {},
        "usage": row.usage_json or {},
        "credits_reserved": row.credits_reserved,
        "credits_used": row.credits_used,
        "error_code": row.error_code,
        "started_at": row.started_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    } for row in rows]}


class SkillRunRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    estimated_credits: int = Field(default=0, ge=0, le=10_000)


def _serialize_run(row: SkillRun) -> dict:
    workflow = (row.evidence_json or {}).get("workflow") or {}
    return {
        "id": row.id,
        "skill_id": row.skill_id,
        "skill_version_id": row.skill_version_id,
        "installation_id": row.installation_id,
        "agent_run_id": row.agent_run_id,
        "trigger_source": row.trigger_source,
        "status": row.status,
        "input_summary": row.input_summary_json or {},
        "output_summary": row.output_summary,
        "output": workflow.get("output"),
        "workflow_status": workflow.get("status"),
        "degraded_steps": workflow.get("degraded_steps") or [],
        "evidence": row.evidence_json or {},
        "usage": row.usage_json or {},
        "credits_reserved": row.credits_reserved,
        "credits_used": row.credits_used,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "trace_id": row.trace_id,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


@router.post("/{slug}/run")
def run_skill(
    slug: str,
    payload: SkillRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        run = invoke_workflow_skill(
            db,
            user=user,
            slug=slug,
            inputs=payload.inputs,
            trigger_source="api",
            estimated_credits=payload.estimated_credits or None,
        )
    except SkillResolutionError as exc:
        _raise_skill_error(exc)
    return {"run": _serialize_run(run)}


@router.get("/runs/{run_id}")
def skill_run_detail(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    row = db.get(SkillRun, run_id)
    if not row or (row.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail={"code": "SKILL_RUN_NOT_FOUND", "message": "Skill run not found"})
    return {"run": _serialize_run(row)}


@router.post("/import")
def import_skill(
    payload: SkillImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    repo_url = None
    commit_hash = None
    if payload.source_type == "github":
        if not payload.repo_url or not payload.commit_hash:
            raise HTTPException(status_code=400, detail={"code": "SKILL_GITHUB_SOURCE_REQUIRED", "message": "repo_url and commit_hash are required"})
        try:
            repo_url, commit_hash = validate_github_source(payload.repo_url, payload.commit_hash)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"code": "SKILL_SOURCE_INVALID", "message": str(exc)}) from exc
    try:
        bundle = validate_skill_bundle(payload.files, trusted_official=user.role == "admin")
        registry = skill_registry(db, user)
        skill, version, created = registry.import_bundle(
            bundle,
            source_type=payload.source_type,
            repo_url=repo_url,
            commit_hash=commit_hash,
            trusted=user.role == "admin" and bundle.manifest.scope in {"official", "marketplace"},
        )
        return {"skill": registry.serialize_skill(skill), "version": version.version, "created": created, "validation": version.validation_json}
    except SkillResolutionError as exc:
        _raise_skill_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "SKILL_VALIDATION_FAILED", "message": str(exc)}) from exc


@router.post("/validate-invocation")
def validate_invocation(
    payload: SkillInvocationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    registry = skill_registry(db, user)
    try:
        resolved = registry.resolve_many(
            payload.skill_refs,
            trigger_source=payload.trigger_source,
            allow_autopilot=payload.allow_autopilot,
            allow_order_intent=payload.allow_order_intent,
        )
        registry.assert_cost(resolved, payload.estimated_credits)
    except SkillResolutionError as exc:
        _raise_skill_error(exc)
    return {
        "valid": True,
        "skills": [item.context_ref() for item in resolved],
        "tool_allowlist": sorted(registry.allowed_tools(resolved)),
        "max_timeout_seconds": min((item.manifest.runtime.timeout_seconds for item in resolved), default=90),
    }


@router.get("/{skill_id}")
def skill_detail(skill_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    registry = skill_registry(db, user)
    try:
        resolved = registry.resolve_many([{"skill_id": skill_id}], enforce_rate_limit=False)
    except SkillResolutionError as exc:
        _raise_skill_error(exc)
    item = resolved[0]
    sources = db.query(SkillSource).filter_by(skill_id=skill_id).order_by(SkillSource.imported_at.desc()).all()
    versions = db.query(SkillVersion).filter_by(skill_id=skill_id).order_by(SkillVersion.created_at.desc()).all()
    return {
        "skill": registry.serialize_skill(item.skill, item.installation),
        "manifest": item.manifest.model_dump(mode="json"),
        "versions": [{"version": row.version, "status": row.release_status, "content_hash": row.content_hash, "validation": row.validation_json, "published_at": row.published_at.isoformat() if row.published_at else None} for row in versions],
        "sources": [{"source_type": row.source_type, "repo_url": row.repo_url, "commit_hash": row.commit_hash, "trust_status": row.trust_status, "imported_at": row.imported_at.isoformat()} for row in sources],
    }


@router.post("/{skill_id}/install")
def install_skill(
    skill_id: str,
    payload: SkillInstallRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    skill = db.get(Skill, skill_id)
    if not skill or skill.status != "published":
        raise HTTPException(status_code=404, detail={"code": "SKILL_NOT_FOUND"})
    registry = skill_registry(db, user)
    try:
        row = registry.install(skill, pinned_version=payload.pinned_version, workspace_id=payload.workspace_id, config_overrides=payload.config_overrides)
    except SkillResolutionError as exc:
        _raise_skill_error(exc)
    return {"installation": serialize_installation(row)}


@router.delete("/installations/{installation_id}")
def uninstall_skill(
    installation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    row = db.query(SkillInstallation).filter_by(id=installation_id, user_id=user.id).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail={"code": "SKILL_INSTALLATION_NOT_FOUND"})
    row.enabled = False
    db.commit()
    return {"ok": True}
