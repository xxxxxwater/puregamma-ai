from __future__ import annotations

import uuid

import pytest
import yaml

from apps.api.services.agent_service import create_conversation, start_run
from apps.api.services.skill_service import skill_registry
from packages.database.models import AgentMessage, SkillRun
from packages.skills.manifest import validate_github_source, validate_skill_bundle


def _bundle(*, skill_id: str | None = None, version: str = "1.0.0", prompt: str = "Use cited market evidence.") -> dict[str, str]:
    manifest = {
        "schema_version": "1.0",
        "skill_id": skill_id or str(uuid.uuid4()),
        "slug": "custom_market_check",
        "name": "Custom Market Check",
        "description": "A safe personal market review Skill.",
        "publisher": "Test User",
        "asset_classes": ["crypto"],
        "data_sources": ["market"],
        "tool_allowlist": ["get_market_quote"],
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        "output_schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
        "prompt_template_ref": "prompts/main.md",
        "risk_level": "low",
        "allow_autopilot": False,
        "allow_order_intent": False,
        "billing_type": "included",
        "version": version,
        "release_status": "draft",
        "scope": "personal",
        "evidence": {"required": True, "require_source_timestamp": True, "require_citation_links": True},
        "runtime": {"max_calls_per_hour": 10, "max_credits_per_run": 30, "timeout_seconds": 60, "human_confirmation_required": False},
    }
    return {".puregamma-skill.yaml": yaml.safe_dump(manifest, sort_keys=False), "prompts/main.md": prompt}


def test_official_registry_resolves_legacy_slugs(db, normal_user):
    registry = skill_registry(db, normal_user)
    catalog = registry.list_visible()
    assert {row["slug"] for row in catalog} >= {
        "market_research", "news_research", "portfolio_review",
        "options_analysis", "source_check", "deep_research",
    }
    resolved = registry.resolve_many(legacy_slugs=["market_research", "news_research"])
    assert [item.manifest.version for item in resolved] == ["1.0.0", "1.0.0"]
    assert registry.allowed_tools(resolved) >= {"get_market_quote", "search_source_documents"}


def test_agent_persists_versioned_skill_refs_and_audit_runs(db, normal_user):
    conversation = create_conversation(db, normal_user)
    run = start_run(
        db,
        normal_user,
        conversation,
        "Review BTC market structure",
        context={"skills": ["market_research"], "data_sources": ["market"]},
    )
    message = db.get(AgentMessage, run.user_message_id)
    assert message.context_json["skills"][0]["slug"] == "market_research"
    assert message.context_json["skills"][0]["version"] == "1.0.0"
    assert message.context_json["skills"][0]["skill_id"]
    audits = db.query(SkillRun).filter_by(agent_run_id=run.id).all()
    assert len(audits) == 1
    assert audits[0].status == "reserved"
    assert audits[0].input_summary_json["content_sha256"]
    assert "Review BTC" not in str(audits[0].input_summary_json)


def test_bundle_rejects_executable_code_and_remote_schema_reference():
    files = _bundle()
    files["src/skill.py"] = "print(1)"
    with pytest.raises(ValueError, match="unsupported Skill bundle path"):
        validate_skill_bundle(files)

    files = _bundle()
    manifest = yaml.safe_load(files[".puregamma-skill.yaml"])
    manifest["input_schema"] = {"$ref": "https://attacker.invalid/schema.json"}
    files[".puregamma-skill.yaml"] = yaml.safe_dump(manifest)
    with pytest.raises(ValueError, match="local JSON Schema references"):
        validate_skill_bundle(files)


def test_non_official_skill_cannot_request_order_intent():
    files = _bundle()
    manifest = yaml.safe_load(files[".puregamma-skill.yaml"])
    manifest.update({"risk_level": "execution_sensitive", "allow_order_intent": True})
    manifest["runtime"]["human_confirmation_required"] = True
    files[".puregamma-skill.yaml"] = yaml.safe_dump(manifest)
    with pytest.raises(ValueError, match="only reviewed official"):
        validate_skill_bundle(files)


def test_github_source_requires_canonical_url_and_full_commit():
    repo, commit = validate_github_source("https://github.com/puregamma/skills", "a" * 40)
    assert repo == "https://github.com/puregamma/skills"
    assert commit == "a" * 40
    with pytest.raises(ValueError):
        validate_github_source("git@github.com:puregamma/skills.git", "main")
