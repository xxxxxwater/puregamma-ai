from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from packages.skills.policy import (
    ALLOWED_ASSET_CLASSES,
    ALLOWED_DATA_SOURCES,
    READ_ONLY_SKILL_TOOLS,
    REVIEWED_OFFICIAL_TOOLS,
    TOOL_DATA_SOURCE_REQUIREMENTS,
)


SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_BUNDLE_BYTES = 512_000
MAX_FILE_BYTES = 128_000
MAX_SCHEMA_DEPTH = 16


class EvidencePolicy(BaseModel):
    required: bool = True
    require_source_timestamp: bool = True
    require_citation_links: bool = True
    allow_insufficient_evidence_result: bool = True


class RuntimeLimits(BaseModel):
    max_calls_per_hour: int = Field(default=30, ge=1, le=10_000)
    max_credits_per_run: int = Field(default=30, ge=0, le=10_000)
    timeout_seconds: int = Field(default=90, ge=5, le=900)
    human_confirmation_required: bool = False


class SkillManifest(BaseModel):
    """Validated phase-one Skill contract. No executable code is represented."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    skill_id: str = Field(min_length=8, max_length=80)
    slug: str = Field(min_length=3, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2_000)
    publisher: str = Field(min_length=1, max_length=160)
    asset_classes: list[str] = Field(default_factory=list, max_length=20)
    data_sources: list[str] = Field(default_factory=list, max_length=30)
    tool_allowlist: list[str] = Field(default_factory=list, max_length=50)
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    output_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    prompt_template_ref: str | None = Field(default=None, max_length=240)
    workflow_template_ref: str | None = Field(default=None, max_length=240)
    strategy_template_ref: str | None = Field(default=None, max_length=240)
    risk_level: Literal["low", "medium", "high", "execution_sensitive"] = "low"
    allow_autopilot: bool = False
    allow_order_intent: bool = False
    billing_type: Literal["free", "included", "paid", "enterprise"] = "included"
    version: str = "1.0.0"
    release_status: Literal["draft", "review", "published", "suspended", "deprecated"] = "draft"
    scope: Literal["personal", "workspace", "official", "marketplace"] = "personal"
    evidence: EvidencePolicy = Field(default_factory=EvidencePolicy)
    runtime: RuntimeLimits = Field(default_factory=RuntimeLimits)
    tags: list[str] = Field(default_factory=list, max_length=30)
    changelog: str = Field(default="", max_length=4_000)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        if not SLUG_RE.fullmatch(value):
            raise ValueError("slug must use lowercase letters, numbers, and underscores")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not SEMVER_RE.fullmatch(value):
            raise ValueError("version must be semantic versioning, for example 1.0.0")
        return value

    @field_validator("asset_classes")
    @classmethod
    def validate_assets(cls, values: list[str]) -> list[str]:
        unknown = set(values) - ALLOWED_ASSET_CLASSES
        if unknown:
            raise ValueError(f"unsupported asset classes: {sorted(unknown)}")
        return list(dict.fromkeys(values))

    @field_validator("data_sources")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        unknown = set(values) - ALLOWED_DATA_SOURCES
        if unknown:
            raise ValueError(f"unsupported data sources: {sorted(unknown)}")
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def validate_security_policy(self) -> "SkillManifest":
        _validate_json_schema(self.input_schema, "input_schema")
        _validate_json_schema(self.output_schema, "output_schema")
        allowed = REVIEWED_OFFICIAL_TOOLS if self.scope == "official" else READ_ONLY_SKILL_TOOLS
        unknown = set(self.tool_allowlist) - allowed
        if unknown:
            raise ValueError(f"tools are not allowed for this scope: {sorted(unknown)}")
        for tool in self.tool_allowlist:
            required_source = TOOL_DATA_SOURCE_REQUIREMENTS.get(tool)
            if required_source and required_source not in self.data_sources:
                raise ValueError(f"{tool} requires the {required_source} data source permission")
        if self.scope != "official" and self.allow_order_intent:
            raise ValueError("only reviewed official Skills may generate order intents")
        if self.allow_order_intent and self.risk_level != "execution_sensitive":
            raise ValueError("order-intent Skills must be execution_sensitive")
        if self.risk_level in {"high", "execution_sensitive"} and not self.runtime.human_confirmation_required:
            raise ValueError("high-risk Skills require human confirmation")
        if self.scope in {"official", "marketplace"} and self.release_status == "published" and not self.publisher:
            raise ValueError("published Skills require a publisher")
        for reference in (self.prompt_template_ref, self.workflow_template_ref, self.strategy_template_ref):
            if reference:
                _validate_reference_path(reference)
        return self


class ValidatedSkillBundle(BaseModel):
    manifest: SkillManifest
    files: dict[str, str]
    content_hash: str
    validation: dict[str, Any]


def _validate_json_schema(schema: dict[str, Any], label: str, *, depth: int = 0) -> None:
    if depth > MAX_SCHEMA_DEPTH:
        raise ValueError(f"{label} exceeds maximum schema depth")
    if not isinstance(schema, dict):
        raise ValueError(f"{label} must be a JSON object")
    encoded = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode()) > MAX_FILE_BYTES:
        raise ValueError(f"{label} is too large")
    schema_type = schema.get("type")
    if schema_type not in {None, "object", "array", "string", "number", "integer", "boolean", "null"}:
        raise ValueError(f"{label} contains an unsupported JSON Schema type")
    if "$ref" in schema:
        reference = schema["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/"):
            raise ValueError(f"{label} may only use local JSON Schema references")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError(f"{label}.properties must be an object")
    for key, child in properties.items():
        if not isinstance(key, str) or not key or len(key) > 120:
            raise ValueError(f"{label} contains an invalid property name")
        _validate_json_schema(child, f"{label}.properties.{key}", depth=depth + 1)
    items = schema.get("items")
    if items is not None:
        _validate_json_schema(items, f"{label}.items", depth=depth + 1)
    required = schema.get("required", [])
    if not isinstance(required, list) or any(item not in properties for item in required):
        raise ValueError(f"{label}.required must reference declared properties")


def validate_json_instance(schema: dict[str, Any], value: Any, label: str = "value") -> None:
    """Small deterministic JSON Schema subset used by the declarative runtime."""
    expected = schema.get("type")
    type_checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    if expected and not type_checks[expected](value):
        raise ValueError(f"{label} must be {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{label} is not an allowed enum value")
    if expected == "object":
        properties = schema.get("properties", {})
        for required in schema.get("required", []):
            if required not in value:
                raise ValueError(f"{label}.{required} is required")
        if schema.get("additionalProperties") is False:
            unknown = set(value) - set(properties)
            if unknown:
                raise ValueError(f"{label} contains unknown properties: {sorted(unknown)}")
        for key, child in properties.items():
            if key in value:
                validate_json_instance(child, value[key], f"{label}.{key}")
    if expected == "array" and "items" in schema:
        for index, item in enumerate(value):
            validate_json_instance(schema["items"], item, f"{label}[{index}]")
    if expected == "string":
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise ValueError(f"{label} is too short")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ValueError(f"{label} is too long")


def _validate_reference_path(value: str) -> None:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("template references must be safe relative paths")


def _allowed_bundle_path(name: str) -> bool:
    if name == ".puregamma-skill.yaml":
        return True
    _validate_reference_path(name)
    path = PurePosixPath(name)
    if not path.parts:
        return False
    root = path.parts[0]
    suffix = path.suffix.lower()
    allowed = {
        "prompts": {".md", ".txt"},
        "strategies": {".yaml", ".yml", ".json"},
        "nautilus": {".yaml", ".yml", ".json"},
        "data-sources": {".yaml", ".yml", ".json"},
        "schemas": {".json"},
        "docs": {".md", ".txt"},
        "examples": {".md", ".json", ".yaml", ".yml"},
    }
    return suffix in allowed.get(root, set())


def validate_skill_bundle(
    files: dict[str, str],
    *,
    trusted_official: bool = False,
) -> ValidatedSkillBundle:
    if ".puregamma-skill.yaml" not in files:
        raise ValueError(".puregamma-skill.yaml is required")
    if not files or len(files) > 100:
        raise ValueError("Skill bundle must contain between 1 and 100 files")
    normalized: dict[str, str] = {}
    total = 0
    for name, content in files.items():
        if not isinstance(name, str) or not _allowed_bundle_path(name):
            raise ValueError(f"unsupported Skill bundle path: {name}")
        if not isinstance(content, str):
            raise ValueError(f"Skill file must be UTF-8 text: {name}")
        size = len(content.encode("utf-8"))
        total += size
        if size > MAX_FILE_BYTES or total > MAX_BUNDLE_BYTES:
            raise ValueError("Skill bundle exceeds the phase-one size limit")
        normalized[name] = content
    try:
        raw_manifest = yaml.safe_load(normalized[".puregamma-skill.yaml"])
    except yaml.YAMLError as exc:
        raise ValueError("Skill manifest is invalid YAML") from exc
    if not isinstance(raw_manifest, dict):
        raise ValueError("Skill manifest must be a YAML object")
    if raw_manifest.get("scope") == "official" and not trusted_official:
        raise ValueError("official Skills require an administrator-reviewed import")
    manifest = SkillManifest.model_validate(raw_manifest)
    for reference in (
        manifest.prompt_template_ref,
        manifest.workflow_template_ref,
        manifest.strategy_template_ref,
    ):
        if reference and reference not in normalized:
            raise ValueError(f"referenced template is missing: {reference}")
    canonical = json.dumps(
        {"manifest": manifest.model_dump(mode="json"), "files": normalized},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return ValidatedSkillBundle(
        manifest=manifest,
        files=normalized,
        content_hash=hashlib.sha256(canonical.encode()).hexdigest(),
        validation={
            "valid": True,
            "schema_version": manifest.schema_version,
            "declarative_only": True,
            "executable_code": False,
            "file_count": len(normalized),
            "total_bytes": total,
        },
    )


def validate_github_source(repo_url: str, commit_hash: str) -> tuple[str, str]:
    normalized_url = repo_url.strip().rstrip("/")
    if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", normalized_url):
        raise ValueError("repo_url must be a canonical HTTPS GitHub repository URL")
    normalized_commit = commit_hash.strip().lower()
    if not COMMIT_RE.fullmatch(normalized_commit):
        raise ValueError("commit_hash must be a full 40-character Git commit hash")
    return normalized_url, normalized_commit
