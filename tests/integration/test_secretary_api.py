from __future__ import annotations

from datetime import datetime, timezone

from packages.agents.chat.tools import ToolResult, ToolSource
from packages.database.models import AgentMessage
from tests.conftest import auth_headers


def test_secretary_browser_use_requires_explicit_current_or_search_cue():
    from apps.api.routers.secretary import _secretary_online_candidate

    assert _secretary_online_candidate("Please search online for the latest BTC news") is True
    assert _secretary_online_candidate("请联网查询目前 BTC 市场新闻") is True
    assert _secretary_online_candidate("How should I discuss a private family matter?") is False


def test_secretary_reply_is_tenant_isolated_metered_and_idempotent(api_client, db, normal_user, max_user):
    request_id = "secretary-idempotency-0001"
    initial_balance = normal_user.credit_balance
    payload = {"content": "Help me plan today's research.", "locale": "en", "request_id": request_id}

    first = api_client.post("/api/secretary/messages", json=payload, headers=auth_headers(normal_user))
    assert first.status_code == 200
    result = first.json()
    assert result["credits_used"] == 20
    assert result["credit_balance"] == initial_balance - 20

    repeated = api_client.post("/api/secretary/messages", json=payload, headers=auth_headers(normal_user))
    assert repeated.status_code == 200
    assert repeated.json()["assistant_message"]["id"] == result["assistant_message"]["id"]
    db.refresh(normal_user)
    assert normal_user.credit_balance == initial_balance - 20

    owner_state = api_client.get("/api/secretary", headers=auth_headers(normal_user))
    other_state = api_client.get("/api/secretary", headers=auth_headers(max_user))
    assert owner_state.status_code == 200
    assert len(owner_state.json()["messages"]) == 2
    assert other_state.status_code == 200
    assert other_state.json()["messages"] == []


def test_secretary_provider_failure_refunds_reservation(api_client, db, normal_user, monkeypatch):
    from apps.api.routers import secretary

    class FailingProvider:
        def complete(self, *args, **kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(secretary, "get_llm_provider", lambda: FailingProvider())
    initial_balance = normal_user.credit_balance
    response = api_client.post(
        "/api/secretary/messages",
        json={"content": "Summarize my day.", "locale": "en", "request_id": "secretary-refund-test-0001"},
        headers=auth_headers(normal_user),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SECRETARY_MODEL_UNAVAILABLE"
    db.refresh(normal_user)
    assert normal_user.credit_balance == initial_balance


def test_secretary_browser_use_prefers_pipeline_then_uses_online_evidence(api_client, db, normal_user, monkeypatch):
    from apps.api.routers import secretary

    monkeypatch.setenv("AGENT_ONLINE_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("ONLINE_SEARCH_PROVIDER", "google_news")
    calls: list[str] = []
    captured: dict[str, str] = {}
    now = datetime.now(timezone.utc)

    def fake_plan(self, query, **kwargs):
        return [("search_source_documents", {"query": query, "symbols": ["BTC"], "providers": ["rss"], "hours": 72})]

    def fake_call(self, name, arguments):
        calls.append(name)
        if name == "search_source_documents":
            return ToolResult(name, [], "PureGamma has no matching synchronized evidence", [])
        assert name == "search_online_sources"
        return ToolResult(
            name,
            [{
                "provider": "google_news_rss",
                "title": "Current BTC market evidence",
                "summary": "A traceable current-source summary.",
                "url": "https://news.google.com/rss/articles/pureg-btc",
                "publishedAt": now.isoformat(),
            }],
            "Retrieved 1 public online source record",
            [ToolSource("google_news_rss", "Current BTC market evidence", "https://news.google.com/rss/articles/pureg-btc", now, now, now)],
        )

    class CapturingProvider:
        def complete(self, prompt, **kwargs):
            captured["prompt"] = prompt
            return "Current evidence is available at the cited source."

    monkeypatch.setattr(secretary.AgentToolRegistry, "plan", fake_plan)
    monkeypatch.setattr(secretary.AgentToolRegistry, "call", fake_call)
    monkeypatch.setattr(secretary, "get_llm_provider", lambda: CapturingProvider())
    response = api_client.post(
        "/api/secretary/messages",
        json={"content": "What is the latest BTC market news?", "locale": "en", "request_id": "secretary-browser-use-0001"},
        headers=auth_headers(normal_user),
    )

    assert response.status_code == 200
    assert calls == ["search_source_documents", "search_online_sources"]
    assert "Current BTC market evidence" in captured["prompt"]
    assistant = db.get(AgentMessage, response.json()["assistant_message"]["id"])
    assert assistant.context_json["research"]["online_used"] is True
    assert assistant.context_json["research"]["tools"][0]["sources"][0]["url"].startswith("https://news.google.com/")
    state = api_client.get("/api/secretary", headers=auth_headers(normal_user)).json()
    browser_use = next(item for item in state["skills"] if item["id"] == "browser-use")
    assert browser_use["status"] == "active"
