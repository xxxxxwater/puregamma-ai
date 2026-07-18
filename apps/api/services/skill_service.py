from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy.orm import Session

from apps.api.services.entitlement_service import get_user_entitlement
from packages.database.models import SkillInstallation, User
from packages.skills.manifest import validate_json_instance
from packages.skills.policy import TOOL_DATA_SOURCE_REQUIREMENTS
from packages.skills.registry import ResolvedSkill, SkillActor, SkillRegistry, update_skill_runs


def skill_actor(db: Session, user: User, *, workspace_ids: set[str] | None = None) -> SkillActor:
    entitlement = get_user_entitlement(db, user.id)
    sources = set(entitlement.get("allowed_data_sources", []))
    if "all" in sources:
        sources = {
            "market", "rss", "fintwit", "x", "x-twitter", "bloomberg",
            "portfolio", "options", "onchain", "defillama",
        }
    return SkillActor(
        user_id=user.id,
        role=user.role,
        plan=entitlement["plan"],
        allowed_data_sources=frozenset(sources),
        workspace_ids=frozenset(workspace_ids or set()),
    )


def skill_registry(db: Session, user: User) -> SkillRegistry:
    return SkillRegistry(db, skill_actor(db, user))


def serialize_installation(row: SkillInstallation) -> dict:
    return {
        "id": row.id,
        "skill_id": row.skill_id,
        "user_id": row.user_id,
        "workspace_id": row.workspace_id,
        "target_type": "workspace" if row.workspace_id else "personal",
        "enabled": row.enabled,
        "pinned_version": row.pinned_version,
        "config_overrides": row.config_overrides_json or {},
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def begin_module_skill_invocation(
    db: Session,
    user: User,
    refs: list[dict] | None,
    *,
    trigger_source: str,
    input_payload: dict,
    estimated_credits: int,
    allow_autopilot: bool = False,
    allow_order_intent: bool = False,
    required_tool: str | None = None,
    invocation_id: str | None = None,
) -> tuple[str, list[ResolvedSkill]]:
    reference = invocation_id or f"{trigger_source}:{uuid.uuid4()}"
    registry = skill_registry(db, user)
    resolved = registry.resolve_many(
        refs or [],
        trigger_source=trigger_source,
        allow_autopilot=allow_autopilot,
        allow_order_intent=allow_order_intent,
    )
    registry.assert_cost(resolved, estimated_credits)
    for item in resolved:
        try:
            validate_json_instance(item.manifest.input_schema, input_payload, "input")
        except ValueError as exc:
            from packages.skills.registry import SkillResolutionError
            raise SkillResolutionError("SKILL_INPUT_INVALID", f"{item.skill.slug}: {exc}", status_code=422) from exc
    if required_tool and resolved and required_tool not in registry.allowed_tools(resolved):
        from packages.skills.registry import SkillResolutionError
        raise SkillResolutionError("SKILL_TOOL_DENIED", f"Selected Skills do not permit {required_tool}", status_code=403)
    required_source = TOOL_DATA_SOURCE_REQUIREMENTS.get(required_tool or "")
    if resolved and required_source and required_source not in registry.actor.allowed_data_sources:
        from packages.skills.registry import SkillResolutionError
        raise SkillResolutionError("SKILL_DATA_SOURCE_DENIED", f"The current plan does not permit {required_source}", status_code=403)
    canonical = json.dumps(input_payload, sort_keys=True, default=str, separators=(",", ":"))
    registry.record_runs(
        resolved,
        external_run_id=reference,
        trace_id=reference,
        trigger_source=trigger_source,
        input_summary={"payload_sha256": hashlib.sha256(canonical.encode()).hexdigest(), "payload_bytes": len(canonical.encode())},
        credits_reserved=estimated_credits,
    )
    return reference, resolved


def finish_module_skill_invocation(
    db: Session,
    invocation_id: str,
    *,
    status: str,
    credits_used: int,
    output_summary: str = "",
    evidence: dict | None = None,
    error_code: str | None = None,
) -> None:
    update_skill_runs(
        db,
        external_run_id=invocation_id,
        status=status,
        credits_used=credits_used,
        output_summary=output_summary,
        evidence=evidence or {},
        error_code=error_code,
    )
