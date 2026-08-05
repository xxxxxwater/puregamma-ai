"""Workflow Skill API tests: run endpoint auth, owner-only run reads, and
credit reservation recording on SkillRun (vertical slice P0-6)."""

from __future__ import annotations

import hashlib

from packages.database.models import MarketEvent, SkillRun, utcnow
from tests.conftest import auth_headers


def _seed_event(db, *, event_type: str, title: str, url: str, kind: str) -> MarketEvent:
    now = utcnow()
    event = MarketEvent(
        event_type=event_type,
        title=title,
        summary="summary",
        source_provider="test_provider",
        source_url=url,
        source_published_at=now,
        collected_at=now,
        data_cutoff_at=now,
        fingerprint=hashlib.sha256(f"{event_type}|{title}".encode()).hexdigest(),
        assets=["BTC"],
        direction="up",
        time_horizon="intraday",
        confidence=0.9,
        evidence_json=[{"kind": kind, "ref": f"test:{title}", "url": url, "published_at": now.isoformat()}],
        evidence_gaps=[],
        status="active",
    )
    db.add(event)
    db.commit()
    return event


def test_run_endpoint_requires_auth(api_client):
    response = api_client.post("/api/skills/overnight_market_brief/run", json={"inputs": {}})
    assert response.status_code == 401


def test_run_endpoint_executes_workflow_and_records_credits(api_client, db, pro_user):
    _seed_event(db, event_type="price_move", title="BTC up 6.2% in 24h", url="https://news.test/btc-move", kind="market_quote")
    _seed_event(db, event_type="news", title="ETF flows hit record", url="https://news.test/etf-flows", kind="news_document")
    response = api_client.post(
        "/api/skills/overnight_market_brief/run",
        json={"inputs": {"locale": "en"}, "estimated_credits": 5},
        headers=auth_headers(pro_user),
    )
    assert response.status_code == 200, response.text
    run = response.json()["run"]
    assert run["status"] == "completed"
    assert run["credits_reserved"] == 5
    assert run["credits_used"] == 5
    assert run["output"]["brief_markdown"]
    assert "BTC up 6.2% in 24h" in run["output"]["brief_markdown"]
    assert run["usage"]["steps_ok"] == 2

    row = db.query(SkillRun).filter_by(id=run["id"]).one()
    assert row.status == "completed"
    assert row.credits_reserved == 5
    assert row.credits_used == 5
    assert row.evidence_json["workflow"]["steps"]
    assert row.trigger_source == "api"

    detail = api_client.get(f"/api/skills/runs/{run['id']}", headers=auth_headers(pro_user))
    assert detail.status_code == 200
    assert detail.json()["run"]["output"]["brief_markdown"] == run["output"]["brief_markdown"]
    assert detail.json()["run"]["evidence"]["workflow"]["evidence_refs"]


def test_run_read_is_owner_or_admin_only(api_client, pro_user, normal_user, admin_user):
    response = api_client.post(
        "/api/skills/execution_monitor/run",
        json={"inputs": {}},
        headers=auth_headers(pro_user),
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["run"]["id"]

    other = api_client.get(f"/api/skills/runs/{run_id}", headers=auth_headers(normal_user))
    assert other.status_code == 404
    assert other.json()["detail"]["code"] == "SKILL_RUN_NOT_FOUND"

    admin = api_client.get(f"/api/skills/runs/{run_id}", headers=auth_headers(admin_user))
    assert admin.status_code == 200
    assert admin.json()["run"]["id"] == run_id

    missing = api_client.get("/api/skills/runs/no-such-run", headers=auth_headers(pro_user))
    assert missing.status_code == 404


def test_run_unknown_slug_returns_404(api_client, normal_user):
    response = api_client.post("/api/skills/no_such_skill/run", json={"inputs": {}}, headers=auth_headers(normal_user))
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "SKILL_NOT_FOUND"


def test_run_validates_inputs_against_manifest_schema(api_client, normal_user):
    response = api_client.post(
        "/api/skills/overnight_market_brief/run",
        json={"inputs": {"locale": "fr"}},
        headers=auth_headers(normal_user),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "SKILL_INPUT_INVALID"


def test_run_estimated_credits_capped_by_manifest_limit(api_client, db, pro_user):
    response = api_client.post(
        "/api/skills/overnight_market_brief/run",
        json={"inputs": {"locale": "en"}, "estimated_credits": 10_000},
        headers=auth_headers(pro_user),
    )
    assert response.status_code == 200, response.text
    run = response.json()["run"]
    # overnight_market_brief runtime limit is 20 credits per run.
    assert run["credits_reserved"] == 20
    assert run["credits_used"] == 20
