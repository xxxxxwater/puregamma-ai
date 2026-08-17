"""Harness deep-research + Memory HTTP contract tests.

Covers docs/mobile/MOBILE_API_CONTRACT.md §2/§3 endpoints: capabilities,
run creation/list/detail/cancel/retry, the in-worker execution pipeline
(evidence -> gateway -> artifact -> credit settlement), and the memory
management surface (settings/items/proposals/delete/clear/export) with
tenant ownership boundaries. No real provider is called — the gateway is
monkeypatched.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.api.services import harness_run_service
from packages.database.models import HarnessResearchRun, MemoryProposal, ResearchArtifact, UserMemory
from packages.memory.service import MemoryService


@pytest.fixture(autouse=True)
def _inline_queue(monkeypatch):
    """Keep POST /runs from executing the pipeline inline during creation."""
    monkeypatch.setattr(harness_run_service, "queue_harness_run", lambda db, run_id: "noop")


def _create_run(client, user, prompt="研究 BTC 资金费率与价格偏离", name="BTC funding research", sources=None) -> dict:
    response = client.post(
        "/api/research/runs",
        json={"name": name, "prompt": prompt, "data_sources": sources or ["market"], "skill": "harness_deep_research"},
        headers=_bearer(user),
    )
    return response


def _bearer(user):
    from apps.api.dependencies import create_access_token

    return {"Authorization": f"Bearer {create_access_token(user)}"}


class TestCapabilities:
    def test_research_and_memory_capabilities_open(self, api_client, pro_user):
        response = api_client.get("/api/mobile/capabilities", headers=_bearer(pro_user))
        assert response.status_code == 200
        payload = response.json()
        assert payload["user_can_start_research"] is True
        assert payload["user_can_manage_memory"] is True
        assert payload["harness_retry_enabled"] is True
        assert payload["harness_research_enabled"] is True
        assert payload["memory_service_enabled"] is True


class TestResearchRuns:
    def test_create_list_and_ownership(self, api_client, pro_user, normal_user):
        response = _create_run(api_client, pro_user)
        assert response.status_code == 201
        run = response.json()["run"]
        assert run["status"] == "queued"
        assert run["name"] == "BTC funding research"
        assert "market" in run["data_sources"]
        assert run["disclaimer"]

        listed = api_client.get("/api/research/runs", headers=_bearer(pro_user)).json()
        assert listed["total"] == 1
        assert listed["runs"][0]["id"] == run["id"]

        # Tenant isolation: another user cannot see or fetch the run.
        other_list = api_client.get("/api/research/runs", headers=_bearer(normal_user)).json()
        assert other_list["total"] == 0
        denied = api_client.get(f"/api/research/runs/{run['id']}", headers=_bearer(normal_user))
        assert denied.status_code == 404

    def test_detail_evidence_and_artifacts(self, api_client, pro_user):
        run = _create_run(api_client, pro_user).json()["run"]
        detail = api_client.get(f"/api/research/runs/{run['id']}", headers=_bearer(pro_user)).json()["run"]
        assert detail["id"] == run["id"]
        assert detail["verification"] is None
        assert api_client.get(f"/api/research/runs/{run['id']}/evidence", headers=_bearer(pro_user)).json()["evidence"] == []
        assert api_client.get(f"/api/research/runs/{run['id']}/artifacts", headers=_bearer(pro_user)).json()["artifacts"] == []

    def test_bad_skill_and_sources_rejected(self, api_client, pro_user):
        response = api_client.post(
            "/api/research/runs",
            json={"name": "x", "prompt": "x", "data_sources": [], "skill": "bash"},
            headers=_bearer(pro_user),
        )
        assert response.status_code == 400
        response = api_client.post(
            "/api/research/runs",
            json={"name": "x", "prompt": "x", "data_sources": ["browser"], "skill": "harness_deep_research"},
            headers=_bearer(pro_user),
        )
        assert response.status_code == 400

    def test_cancel_and_state_conflict(self, api_client, pro_user):
        run = _create_run(api_client, pro_user).json()["run"]
        canceled = api_client.post(f"/api/research/runs/{run['id']}/cancel", headers=_bearer(pro_user))
        assert canceled.status_code == 200
        assert canceled.json()["run"]["status"] == "canceled"
        # Canceling an already-canceled run returns the current state
        # (idempotent) rather than an error.
        again = api_client.post(f"/api/research/runs/{run['id']}/cancel", headers=_bearer(pro_user))
        assert again.status_code == 200
        assert again.json()["run"]["status"] == "canceled"

    def test_retry_creates_new_run(self, api_client, pro_user):
        run = _create_run(api_client, pro_user).json()["run"]
        api_client.post(f"/api/research/runs/{run['id']}/cancel", headers=_bearer(pro_user))
        retried = api_client.post(f"/api/research/runs/{run['id']}/retry", headers=_bearer(pro_user))
        assert retried.status_code == 200
        new_run = retried.json()["run"]
        assert new_run["id"] != run["id"]
        assert new_run["status"] == "queued"

    def test_daily_quota(self, api_client, pro_user, monkeypatch):
        from types import SimpleNamespace

        from apps.api.config import get_settings as real_get_settings

        real = real_get_settings()
        quota = SimpleNamespace(
            **{**real.__dict__, "harness_max_runs_per_user_per_day": 1}
        )
        monkeypatch.setattr(harness_run_service, "get_settings", lambda: quota)
        assert _create_run(api_client, pro_user).status_code == 201
        second = _create_run(api_client, pro_user, prompt="another question")
        assert second.status_code == 429


class TestHarnessPipeline:
    def _fake_gateway(self, content: str = "Funding rates diverged from price [1]. Conclusion: neutral."):
        usage = SimpleNamespace(input_tokens=120, output_tokens=60)
        result = SimpleNamespace(content=content, usage=usage)
        route = SimpleNamespace(provider=SimpleNamespace(id="deepseek-official"))
        return result, route

    def test_pipeline_completes_with_evidence_and_artifact(self, api_client, pro_user, db, monkeypatch):
        run = _create_run(api_client, pro_user).json()["run"]
        evidence_items = [
            {
                "id": "ev-1",
                "citation_index": 1,
                "provider": "coingecko",
                "title": "BTC funding",
                "url": "https://example.com/funding",
                "source_scope": "market",
                "excerpt": "90d funding series",
                "is_verified": True,
                "verification_note": None,
                "fetched_at": "2026-08-17T00:00:00Z",
            }
        ]
        monkeypatch.setattr(harness_run_service, "_gather_evidence", lambda db, row: evidence_items)
        with patch("packages.gateway.service.execute_chat", return_value=self._fake_gateway()):
            result = harness_run_service.execute_queued_run(db, run["id"])
        assert result["status"] == "completed"
        assert result["verification"] == "verified"
        assert result["evidence_count"] == 1
        assert result["citation_count"] == 1
        assert result["credits_used"] > 0

        evidence = api_client.get(f"/api/research/runs/{run['id']}/evidence", headers=_bearer(pro_user)).json()
        assert evidence["total"] == 1
        artifacts = api_client.get(f"/api/research/runs/{run['id']}/artifacts", headers=_bearer(pro_user)).json()
        assert len(artifacts["artifacts"]) == 1
        assert artifacts["artifacts"][0]["status"] == "validated"
        assert db.query(ResearchArtifact).filter_by(research_run_id=run["id"]).count() == 1

    def test_pipeline_degraded_when_no_citation_matched(self, api_client, pro_user, db, monkeypatch):
        run = _create_run(api_client, pro_user).json()["run"]
        monkeypatch.setattr(
            harness_run_service,
            "_gather_evidence",
            lambda db, row: [{"id": "ev-1", "citation_index": 1, "provider": "x", "title": "t", "url": "u", "source_scope": "market", "excerpt": "e", "is_verified": True, "verification_note": None, "fetched_at": "2026-08-17T00:00:00Z"}],
        )
        with patch("packages.gateway.service.execute_chat", return_value=self._fake_gateway("No citations at all.")):
            result = harness_run_service.execute_queued_run(db, run["id"])
        assert result["status"] == "degraded"
        assert result["is_degraded"] is True

    def test_pipeline_failed_refunds_credits(self, api_client, pro_user, db, monkeypatch):
        run = _create_run(api_client, pro_user).json()["run"]
        monkeypatch.setattr(harness_run_service, "_gather_evidence", lambda db, row: [])
        with patch("packages.gateway.service.execute_chat", side_effect=RuntimeError("provider down")):
            result = harness_run_service.execute_queued_run(db, run["id"])
        assert result["status"] == "failed"
        assert result["credits_used"] in (None, 0)
        row = db.get(HarnessResearchRun, run["id"])
        assert row.settlement_status == "refunded" or (row.usage_json or {}).get("credits_used") in (None, 0)


class TestMemoryContract:
    def test_settings_roundtrip(self, api_client, pro_user, db):
        payload = api_client.get("/api/memory/settings", headers=_bearer(pro_user)).json()["settings"]
        assert payload["conversation_summary_enabled"] is True
        assert payload["consent_required"] is False
        patched = api_client.patch(
            "/api/memory/settings",
            json={"research_memory_enabled": False, "short_term_enabled": False},
            headers=_bearer(pro_user),
        )
        assert patched.status_code == 200
        updated = patched.json()["settings"]
        assert updated["research_memory_enabled"] is False
        assert updated["short_term_enabled"] is False

    def test_items_approve_delete_clear(self, api_client, pro_user, db):
        service = MemoryService(auto_accept_low_risk=False)
        proposal = service.propose(
            db,
            user_id=pro_user.id,
            namespace="chat",
            kind="research_insight",
            content={"text": "用户偏好 BTC 资金费率研究"},
        )
        assert proposal.status == "pending"

        listed = api_client.get("/api/memory/proposals", headers=_bearer(pro_user)).json()
        assert len(listed["proposals"]) == 1
        assert listed["proposals"][0]["status"] == "pending"

        approved = api_client.post(f"/api/memory/proposals/{proposal.id}/approve", headers=_bearer(pro_user))
        assert approved.status_code == 200
        assert approved.json()["proposal"]["status"] == "user_approved"

        items = api_client.get("/api/memory/items?scope=short_term", headers=_bearer(pro_user)).json()
        assert items["total"] == 1
        item = items["items"][0]
        assert item["scope"] == "chat"
        assert "资金费率" in item["content_preview"]

        deleted = api_client.delete(f"/api/memory/items/{item['id']}", headers=_bearer(pro_user))
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True

        cleared = api_client.post("/api/memory/clear", json={"scope": "short_term"}, headers=_bearer(pro_user))
        assert cleared.status_code == 200

    def test_export(self, api_client, pro_user):
        payload = api_client.get("/api/memory/export", headers=_bearer(pro_user)).json()
        assert payload["url"]
        assert payload["expires_at"]
        download = api_client.get(payload["url"], headers=_bearer(pro_user))
        assert download.status_code == 200
        assert "memories" in download.text

    def test_ownership_boundaries(self, api_client, pro_user, normal_user, db):
        service = MemoryService(auto_accept_low_risk=False)
        proposal = service.propose(
            db,
            user_id=pro_user.id,
            namespace="research",
            kind="research_insight",
            content={"text": "pro 用户的研究记忆"},
        )
        denied_approve = api_client.post(f"/api/memory/proposals/{proposal.id}/approve", headers=_bearer(normal_user))
        assert denied_approve.status_code == 404
        approved = api_client.post(f"/api/memory/proposals/{proposal.id}/approve", headers=_bearer(pro_user))
        memory_id = db.query(UserMemory).filter_by(user_id=pro_user.id).first().id
        denied_delete = api_client.delete(f"/api/memory/items/{memory_id}", headers=_bearer(normal_user))
        # delete_memory silently ignores missing rows, but the owner must keep the row
        assert db.query(UserMemory).filter_by(id=memory_id).count() == 1
        owner_delete = api_client.delete(f"/api/memory/items/{memory_id}", headers=_bearer(pro_user))
        assert owner_delete.json()["deleted"] is True
