from __future__ import annotations

import uuid

import yaml

from packages.database.models import SkillRun
from tests.conftest import auth_headers


def _payload(skill_id: str, *, prompt: str = "Use market evidence.") -> dict:
    manifest = {
        "schema_version": "1.0",
        "skill_id": skill_id,
        "slug": "private_market_review",
        "name": "Private Market Review",
        "description": "A personal declarative market research workflow.",
        "publisher": "Private User",
        "asset_classes": ["crypto"],
        "data_sources": ["market"],
        "tool_allowlist": ["get_market_quote", "get_data_source_status"],
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        "output_schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
        "prompt_template_ref": "prompts/review.md",
        "risk_level": "low",
        "allow_autopilot": False,
        "allow_order_intent": False,
        "billing_type": "included",
        "version": "1.0.0",
        "release_status": "draft",
        "scope": "personal",
        "runtime": {"max_calls_per_hour": 20, "max_credits_per_run": 30, "timeout_seconds": 60, "human_confirmation_required": False},
    }
    return {
        "source_type": "github",
        "repo_url": "https://github.com/puregamma/private-skills",
        "commit_hash": "b" * 40,
        "files": {".puregamma-skill.yaml": yaml.safe_dump(manifest, sort_keys=False), "prompts/review.md": prompt},
    }


def test_skill_catalog_import_version_conflict_and_tenant_isolation(api_client, normal_user, pro_user):
    catalog = api_client.get("/api/skills", headers=auth_headers(normal_user))
    assert catalog.status_code == 200
    assert len(catalog.json()["skills"]) >= 6

    skill_id = str(uuid.uuid4())
    payload = _payload(skill_id)
    created = api_client.post("/api/skills/import", json=payload, headers=auth_headers(normal_user))
    assert created.status_code == 200, created.text
    assert created.json()["created"] is True
    assert created.json()["skill"]["scope"] == "personal"

    repeated = api_client.post("/api/skills/import", json=payload, headers=auth_headers(normal_user))
    assert repeated.status_code == 200
    assert repeated.json()["created"] is False

    conflict = api_client.post("/api/skills/import", json=_payload(skill_id, prompt="Changed content"), headers=auth_headers(normal_user))
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "SKILL_VERSION_CONFLICT"

    own_detail = api_client.get(f"/api/skills/{skill_id}", headers=auth_headers(normal_user))
    assert own_detail.status_code == 200
    assert own_detail.json()["sources"][0]["commit_hash"] == "b" * 40

    denied = api_client.get(f"/api/skills/{skill_id}", headers=auth_headers(pro_user))
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "SKILL_ACCESS_DENIED"


def test_skill_invocation_validation_returns_resolved_version(api_client, normal_user):
    catalog = api_client.get("/api/skills", headers=auth_headers(normal_user)).json()["skills"]
    market = next(item for item in catalog if item["slug"] == "market_research")
    response = api_client.post(
        "/api/skills/validate-invocation",
        json={"skill_refs": [{"skill_id": market["skill_id"], "version": market["current_version"]}], "trigger_source": "dashboard", "estimated_credits": 2},
        headers=auth_headers(normal_user),
    )
    assert response.status_code == 200, response.text
    assert response.json()["skills"][0]["version"] == "1.1.0"
    assert "get_market_quote" in response.json()["tool_allowlist"]
    assert "search_source_documents" in response.json()["tool_allowlist"]

    first_install = api_client.post(
        f"/api/skills/{market['skill_id']}/install",
        json={"pinned_version": market["current_version"]},
        headers=auth_headers(normal_user),
    )
    second_install = api_client.post(
        f"/api/skills/{market['skill_id']}/install",
        json={"pinned_version": market["current_version"]},
        headers=auth_headers(normal_user),
    )
    assert first_install.status_code == second_install.status_code == 200
    assert first_install.json()["installation"]["id"] == second_install.json()["installation"]["id"]


def test_skill_import_rejects_code_file(api_client, normal_user):
    payload = _payload(str(uuid.uuid4()))
    payload["files"]["scripts/run.py"] = "raise SystemExit"
    response = api_client.post("/api/skills/import", json=payload, headers=auth_headers(normal_user))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "SKILL_VALIDATION_FAILED"


def test_user_cannot_replace_official_skill_id(api_client, normal_user):
    catalog = api_client.get("/api/skills", headers=auth_headers(normal_user)).json()["skills"]
    official = next(item for item in catalog if item["slug"] == "market_research")
    payload = _payload(official["skill_id"])
    response = api_client.post("/api/skills/import", json=payload, headers=auth_headers(normal_user))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SKILL_OWNERSHIP_CONFLICT"


def test_backtest_module_uses_registry_and_writes_skill_audit(api_client, db, pro_user):
    catalog = api_client.get("/api/skills", headers=auth_headers(pro_user)).json()["skills"]
    deep = next(item for item in catalog if item["slug"] == "deep_research")
    response = api_client.post(
        "/backtest",
        json={
            "strategy_name": "BTC momentum breakout",
            "asset": "BTC",
            "engine": "mock",
            "idempotency_key": "skill-backtest-1",
            "skill_refs": [{"skill_id": deep["skill_id"], "version": "1.0.0"}],
        },
        headers=auth_headers(pro_user),
    )
    assert response.status_code == 200, response.text
    audit = db.query(SkillRun).filter_by(user_id=pro_user.id, trigger_source="nautilus").one()
    assert audit.status == "completed"
    assert audit.credits_used == response.json()["backtest"]["credits_spent"]
    assert audit.evidence_json["backtest_id"] == response.json()["backtest"]["id"]


def test_report_module_uses_registry_and_order_preview_fails_closed(api_client, db, normal_user):
    catalog = api_client.get("/api/skills", headers=auth_headers(normal_user)).json()["skills"]
    market = next(item for item in catalog if item["slug"] == "market_research")
    report = api_client.post(
        "/reports/event",
        json={"asset": "BTC", "event": "ETF flow update", "skill_refs": [{"skill_id": market["skill_id"], "version": market["current_version"]}]},
        headers=auth_headers(normal_user),
    )
    assert report.status_code == 200, report.text
    audit = db.query(SkillRun).filter_by(user_id=normal_user.id, trigger_source="report").one()
    assert audit.status == "completed"
    assert audit.evidence_json["report_id"] == report.json()["report"]["id"]

    preview = api_client.post(
        "/strategies/not-a-strategy/paper",
        json={"mode": "PAPER", "skill_refs": [{"skill_id": market["skill_id"], "version": market["current_version"]}]},
        headers=auth_headers(normal_user),
    )
    assert preview.status_code == 403
    assert preview.json()["detail"]["code"] == "SKILL_ORDER_INTENT_DENIED"
