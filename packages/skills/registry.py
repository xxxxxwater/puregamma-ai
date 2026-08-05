from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from packages.database.models import (
    Skill,
    SkillInstallation,
    SkillPermission,
    SkillRun,
    SkillSource,
    SkillVersion,
    utcnow,
)
from packages.skills.manifest import SkillManifest, ValidatedSkillBundle, validate_json_instance


class SkillResolutionError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class SkillActor:
    user_id: str
    role: str
    plan: str
    allowed_data_sources: frozenset[str]
    workspace_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ResolvedSkill:
    skill: Skill
    version: SkillVersion
    manifest: SkillManifest
    installation: SkillInstallation | None

    def context_ref(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill.id,
            "slug": self.skill.slug,
            "version": self.version.version,
            "installation_id": self.installation.id if self.installation else None,
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SkillRegistry:
    """Project-wide resolver for Chat, reports, portfolio, jobs, and runtime callers."""

    def __init__(self, db: Session, actor: SkillActor):
        self.db = db
        self.actor = actor

    def visible_query(self):
        installed_ids = self.db.query(SkillInstallation.skill_id).filter(
            SkillInstallation.user_id == self.actor.user_id,
            SkillInstallation.enabled.is_(True),
        )
        predicates = [
            Skill.scope == "official",
            (Skill.scope == "marketplace") & (Skill.status == "published"),
            Skill.id.in_(installed_ids),
            (Skill.scope == "personal") & (Skill.owner_user_id == self.actor.user_id),
        ]
        if self.actor.workspace_ids:
            predicates.append(
                (Skill.scope == "workspace") & Skill.workspace_id.in_(self.actor.workspace_ids)
            )
        return self.db.query(Skill).filter(or_(*predicates))

    def list_visible(self, *, include_disabled: bool = False) -> list[dict[str, Any]]:
        query = self.visible_query()
        if not include_disabled:
            query = query.filter(Skill.status.in_(["published", "draft", "review"]))
        rows = query.order_by(Skill.scope, Skill.name, Skill.slug).all()
        installations = {
            row.skill_id: row
            for row in self.db.query(SkillInstallation)
            .filter(
                SkillInstallation.user_id == self.actor.user_id,
                SkillInstallation.enabled.is_(True),
            )
            .all()
        }
        return [self.serialize_skill(row, installations.get(row.id)) for row in rows]

    def serialize_skill(
        self, row: Skill, installation: SkillInstallation | None = None
    ) -> dict[str, Any]:
        version = self._version(row, installation.pinned_version if installation else None)
        manifest = SkillManifest.model_validate(version.manifest_json)
        return {
            "skill_id": row.id,
            "slug": row.slug,
            "name": row.name,
            "description": row.description,
            "publisher": row.publisher_name,
            "scope": row.scope,
            "status": row.status,
            "current_version": version.version,
            "asset_classes": manifest.asset_classes,
            "data_sources": manifest.data_sources,
            "tool_allowlist": manifest.tool_allowlist,
            "risk_level": manifest.risk_level,
            "allow_autopilot": manifest.allow_autopilot,
            "allow_order_intent": manifest.allow_order_intent,
            "billing_type": manifest.billing_type,
            "evidence": manifest.evidence.model_dump(),
            "runtime": manifest.runtime.model_dump(),
            "installation_id": installation.id if installation else None,
            "installed": installation is not None,
            "enabled": installation.enabled if installation else row.scope == "official",
        }

    def _version(self, skill: Skill, requested_version: str | None = None) -> SkillVersion:
        version_name = requested_version or skill.current_version
        row = (
            self.db.query(SkillVersion)
            .filter_by(skill_id=skill.id, version=version_name)
            .one_or_none()
        )
        if not row:
            raise SkillResolutionError("SKILL_VERSION_NOT_FOUND", "Skill version not found", status_code=404)
        if row.release_status in {"suspended", "deprecated"}:
            raise SkillResolutionError("SKILL_VERSION_UNAVAILABLE", "Skill version is unavailable", status_code=409)
        return row

    def _installation(self, skill_id: str, installation_id: str | None) -> SkillInstallation | None:
        query = self.db.query(SkillInstallation).filter(
            SkillInstallation.skill_id == skill_id,
            SkillInstallation.enabled.is_(True),
        )
        if installation_id:
            query = query.filter(SkillInstallation.id == installation_id)
        query = query.filter(
            or_(
                SkillInstallation.user_id == self.actor.user_id,
                SkillInstallation.workspace_id.in_(self.actor.workspace_ids)
                if self.actor.workspace_ids
                else SkillInstallation.workspace_id == "__no_workspace__",
            )
        )
        return query.first()

    def _assert_visible(self, skill: Skill, installation: SkillInstallation | None) -> None:
        if skill.scope == "official":
            return
        if skill.scope == "personal" and skill.owner_user_id == self.actor.user_id:
            return
        if skill.scope == "workspace" and skill.workspace_id in self.actor.workspace_ids:
            return
        if skill.scope == "marketplace" and installation:
            return
        if installation:
            return
        raise SkillResolutionError("SKILL_ACCESS_DENIED", "Skill is not installed or visible", status_code=403)

    def resolve_many(
        self,
        refs: Iterable[dict[str, Any]] | None = None,
        *,
        legacy_slugs: Iterable[str] | None = None,
        trigger_source: str = "agent_chat",
        allow_autopilot: bool = False,
        allow_order_intent: bool = False,
        enforce_rate_limit: bool = True,
    ) -> list[ResolvedSkill]:
        requests = list(refs or [])[:8]
        if not requests:
            requests = [{"slug": slug} for slug in list(legacy_slugs or [])[:8]]
        resolved: list[ResolvedSkill] = []
        seen: set[str] = set()
        for request in requests:
            skill_id = str(request.get("skill_id") or "").strip()
            slug = str(request.get("slug") or "").strip()
            if not skill_id and not slug:
                raise SkillResolutionError("SKILL_REFERENCE_INVALID", "Skill reference requires skill_id or slug")
            query = self.db.query(Skill)
            skill = query.filter(Skill.id == skill_id).one_or_none() if skill_id else query.filter(Skill.slug == slug).one_or_none()
            if not skill:
                raise SkillResolutionError("SKILL_NOT_FOUND", f"Skill not found: {skill_id or slug}", status_code=404)
            if skill.id in seen:
                continue
            installation = self._installation(skill.id, request.get("installation_id"))
            self._assert_visible(skill, installation)
            requested_version = request.get("version") or (installation.pinned_version if installation else None)
            version = self._version(skill, str(requested_version) if requested_version else None)
            manifest = SkillManifest.model_validate(version.manifest_json)
            if skill.status not in {"published", "draft", "review"}:
                raise SkillResolutionError("SKILL_UNAVAILABLE", "Skill is not available", status_code=409)
            if skill.status != "published" and skill.owner_user_id != self.actor.user_id and self.actor.role != "admin":
                raise SkillResolutionError("SKILL_NOT_PUBLISHED", "Skill has not been published", status_code=403)
            if allow_autopilot and not manifest.allow_autopilot:
                raise SkillResolutionError("SKILL_AUTOPILOT_DENIED", "Skill is not approved for Autopilot", status_code=403)
            if allow_order_intent and not manifest.allow_order_intent:
                raise SkillResolutionError("SKILL_ORDER_INTENT_DENIED", "Skill cannot generate order intents", status_code=403)
            if trigger_source == "agent_chat" and manifest.runtime.human_confirmation_required:
                raise SkillResolutionError("SKILL_CONFIRMATION_REQUIRED", "This Skill requires a reviewed confirmation workflow", status_code=409)
            if manifest.billing_type == "enterprise" and self.actor.plan.lower() != "enterprise":
                raise SkillResolutionError("SKILL_PLAN_REQUIRED", "Enterprise plan is required", status_code=403)
            if enforce_rate_limit:
                since = _now() - timedelta(hours=1)
                count = self.db.query(SkillRun).filter(
                    SkillRun.skill_id == skill.id,
                    SkillRun.user_id == self.actor.user_id,
                    SkillRun.started_at >= since,
                    SkillRun.status.notin_(["rejected"]),
                ).count()
                if count >= manifest.runtime.max_calls_per_hour:
                    raise SkillResolutionError("SKILL_RATE_LIMITED", "Skill hourly invocation limit reached", status_code=429)
            resolved.append(ResolvedSkill(skill, version, manifest, installation))
            seen.add(skill.id)
        return resolved

    @staticmethod
    def allowed_tools(resolved: Iterable[ResolvedSkill]) -> set[str]:
        return set().union(*(set(item.manifest.tool_allowlist) for item in resolved))

    @staticmethod
    def prompt_instructions(resolved: Iterable[ResolvedSkill]) -> str:
        blocks: list[str] = []
        for item in resolved:
            reference = item.manifest.prompt_template_ref
            content = (item.version.content_bundle_json or {}).get(reference, "") if reference else ""
            if content:
                blocks.append(f"SKILL {item.skill.slug}@{item.version.version}:\n{content[:6000]}")
        return "\n\n".join(blocks)

    @staticmethod
    def assert_cost(resolved: Iterable[ResolvedSkill], credits: int) -> None:
        for item in resolved:
            if credits > item.manifest.runtime.max_credits_per_run:
                raise SkillResolutionError(
                    "SKILL_COST_LIMIT_EXCEEDED",
                    f"Estimated cost exceeds {item.skill.slug} runtime limit",
                    status_code=402,
                )

    @staticmethod
    def validate_chat_contract(resolved: Iterable[ResolvedSkill], content: str) -> None:
        for item in resolved:
            try:
                validate_json_instance(item.manifest.input_schema, {"query": content}, "input")
                validate_json_instance(
                    item.manifest.output_schema,
                    {"answer": "validated at runtime", "citations": []},
                    "output",
                )
            except ValueError as exc:
                raise SkillResolutionError(
                    "SKILL_SCHEMA_INCOMPATIBLE",
                    f"{item.skill.slug} is not compatible with Agent Chat: {exc}",
                    status_code=422,
                ) from exc

    def record_runs(
        self,
        resolved: Iterable[ResolvedSkill],
        *,
        agent_run_id: str | None = None,
        external_run_id: str | None = None,
        trace_id: str,
        trigger_source: str,
        input_summary: dict[str, Any],
        credits_reserved: int,
    ) -> list[SkillRun]:
        if not agent_run_id and not external_run_id:
            raise ValueError("agent_run_id or external_run_id is required")
        rows: list[SkillRun] = []
        resolved_list = list(resolved)
        allocation = credits_reserved // max(1, len(resolved_list))
        remainder = credits_reserved - (allocation * len(resolved_list))
        for index, item in enumerate(resolved_list):
            run_reference = agent_run_id or external_run_id
            key = f"skill-run:{run_reference}:{item.skill.id}:{item.version.version}"
            existing = self.db.query(SkillRun).filter_by(idempotency_key=key).one_or_none()
            if existing:
                rows.append(existing)
                continue
            row = SkillRun(
                skill_id=item.skill.id,
                skill_version_id=item.version.id,
                installation_id=item.installation.id if item.installation else None,
                user_id=self.actor.user_id,
                workspace_id=item.skill.workspace_id,
                agent_run_id=agent_run_id,
                external_run_id=external_run_id,
                trigger_source=trigger_source,
                status="reserved",
                input_summary_json=input_summary,
                evidence_json={},
                usage_json={},
                credits_reserved=allocation + (remainder if index == 0 else 0),
                credits_used=0,
                trace_id=trace_id,
                idempotency_key=key,
            )
            self.db.add(row)
            rows.append(row)
        return rows

    def install(
        self,
        skill: Skill,
        *,
        pinned_version: str | None = None,
        workspace_id: str | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> SkillInstallation:
        if skill.scope != "marketplace":
            self._assert_visible(skill, self._installation(skill.id, None))
        if workspace_id and workspace_id not in self.actor.workspace_ids and self.actor.role != "admin":
            raise SkillResolutionError("WORKSPACE_ACCESS_DENIED", "Workspace membership is required", status_code=403)
        if pinned_version:
            self._version(skill, pinned_version)
        target_key = f"workspace:{workspace_id}" if workspace_id else f"user:{self.actor.user_id}"
        query = self.db.query(SkillInstallation).filter_by(skill_id=skill.id, target_key=target_key)
        row = query.one_or_none()
        if not row:
            row = SkillInstallation(
                skill_id=skill.id,
                user_id=None if workspace_id else self.actor.user_id,
                workspace_id=workspace_id,
                installed_by_user_id=self.actor.user_id,
                target_key=target_key,
            )
            self.db.add(row)
        row.enabled = True
        row.pinned_version = pinned_version
        row.config_overrides_json = config_overrides or {}
        self.db.commit()
        self.db.refresh(row)
        return row

    def import_bundle(
        self,
        bundle: ValidatedSkillBundle,
        *,
        source_type: str,
        repo_url: str | None,
        commit_hash: str | None,
        trusted: bool,
    ) -> tuple[Skill, SkillVersion, bool]:
        manifest = bundle.manifest
        if manifest.scope in {"official", "marketplace"} and self.actor.role != "admin":
            raise SkillResolutionError("SKILL_PUBLISH_DENIED", "Administrator review is required", status_code=403)
        if manifest.scope == "workspace" and self.actor.role != "admin":
            raise SkillResolutionError("WORKSPACE_ACCESS_DENIED", "Workspace publishing requires workspace administration", status_code=403)
        existing = self.db.get(Skill, manifest.skill_id)
        if existing and self.actor.role != "admin" and (
            existing.scope in {"official", "marketplace"}
            or existing.owner_user_id != self.actor.user_id
        ):
            raise SkillResolutionError("SKILL_OWNERSHIP_CONFLICT", "Skill ID belongs to another owner", status_code=409)
        slug_owner = self.db.query(Skill).filter(Skill.slug == manifest.slug, Skill.id != manifest.skill_id).first()
        if slug_owner:
            raise SkillResolutionError("SKILL_SLUG_CONFLICT", "Skill slug is already registered", status_code=409)
        same_version = self.db.query(SkillVersion).filter_by(skill_id=manifest.skill_id, version=manifest.version).one_or_none()
        if same_version:
            if same_version.content_hash != bundle.content_hash:
                raise SkillResolutionError("SKILL_VERSION_CONFLICT", "Version already exists with different content", status_code=409)
            return existing, same_version, False
        skill = existing or Skill(id=manifest.skill_id)
        skill.slug = manifest.slug
        skill.name = manifest.name
        skill.description = manifest.description
        skill.publisher_name = manifest.publisher
        skill.owner_user_id = None if manifest.scope in {"official", "marketplace"} else self.actor.user_id
        skill.workspace_id = None
        skill.scope = manifest.scope
        skill.status = manifest.release_status
        skill.current_version = manifest.version
        skill.asset_classes_json = manifest.asset_classes
        skill.risk_level = manifest.risk_level
        skill.billing_type = manifest.billing_type
        skill.allow_autopilot = manifest.allow_autopilot
        skill.allow_order_intent = manifest.allow_order_intent
        self.db.add(skill)
        self.db.flush()
        version = SkillVersion(
            skill_id=skill.id,
            version=manifest.version,
            manifest_json=manifest.model_dump(mode="json"),
            content_bundle_json=bundle.files,
            content_hash=bundle.content_hash,
            release_status=manifest.release_status,
            changelog=manifest.changelog,
            validation_json=bundle.validation,
            created_by_user_id=self.actor.user_id,
            published_at=utcnow() if manifest.release_status == "published" else None,
        )
        self.db.add(version)
        self.db.flush()
        for source in manifest.data_sources:
            self.db.add(SkillPermission(skill_id=skill.id, skill_version_id=version.id, permission_type="data_source", resource=source, effect="allow", constraints_json={}))
        for tool in manifest.tool_allowlist:
            self.db.add(SkillPermission(skill_id=skill.id, skill_version_id=version.id, permission_type="tool", resource=tool, effect="allow", constraints_json={}))
        self.db.add(SkillSource(
            skill_id=skill.id,
            skill_version_id=version.id,
            source_type=source_type,
            repo_url=repo_url,
            commit_hash=commit_hash,
            trust_status="trusted" if trusted else "untrusted",
            imported_by_user_id=self.actor.user_id,
            metadata_json={"declarative_only": True, "content_hash": bundle.content_hash},
        ))
        self.db.commit()
        self.db.refresh(skill)
        self.db.refresh(version)
        return skill, version, True


def invocation_input_summary(content: str, data_sources: list[str]) -> dict[str, Any]:
    return {
        "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "content_length": len(content),
        "data_sources": data_sources,
    }


def update_skill_runs(
    db: Session,
    agent_run_id: str | None = None,
    *,
    external_run_id: str | None = None,
    status: str,
    credits_used: int | None = None,
    output_summary: str | None = None,
    evidence: dict[str, Any] | None = None,
    usage: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    if not agent_run_id and not external_run_id:
        raise ValueError("agent_run_id or external_run_id is required")
    query = db.query(SkillRun)
    rows = query.filter_by(agent_run_id=agent_run_id).all() if agent_run_id else query.filter_by(external_run_id=external_run_id).all()
    if not rows:
        return
    allocation = (credits_used or 0) // len(rows)
    remainder = (credits_used or 0) - allocation * len(rows)
    terminal = status in {"completed", "failed", "canceled", "interrupted", "rejected"}
    for index, row in enumerate(rows):
        row.status = status
        if credits_used is not None:
            row.credits_used = allocation + (remainder if index == 0 else 0)
        if output_summary is not None:
            row.output_summary = output_summary[:2_000]
        if evidence is not None:
            row.evidence_json = evidence
        if usage is not None:
            row.usage_json = usage
        row.error_code = error_code
        row.error_message = error_message[:1_000] if error_message else None
        if status == "running" and not row.started_at:
            row.started_at = utcnow()
        if terminal:
            row.completed_at = utcnow()
