from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from apps.api.config import Settings
from apps.api.services import agent_service
from packages.agents.chat.tools import AgentToolRegistry
from packages.agents.llm.mock_provider import MockLLMProvider
from packages.data.online_research_provider import (
    GOOGLE_NEWS_SEARCH_URL,
    OnlineResearchProvider,
    OnlineResearchResult,
    sanitize_online_query,
)
from packages.data.provider import ProviderError
from packages.database.models import AgentMessageSource, AgentToolCall


def test_google_news_online_search_is_fixed_host_metadata_only(monkeypatch):
    monkeypatch.setenv("AGENT_ONLINE_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("ONLINE_SEARCH_PROVIDER", "google_news")
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Bitcoin market update - Example News</title>
      <link>https://news.google.com/rss/articles/example</link>
      <description>Spot demand increased during the session.</description>
      <pubDate>Sat, 18 Jul 2026 10:00:00 GMT</pubDate>
      <source url="https://example.com">Example News</source></item>
      <item><title>Unsafe result</title><link>http://127.0.0.1/internal</link></item>
    </channel></rss>"""

    def fake_get(url: str, **kwargs):
        assert url == GOOGLE_NEWS_SEARCH_URL
        assert kwargs["follow_redirects"] is False
        assert kwargs["params"]["q"] == "latest BTC market"
        return httpx.Response(200, content=rss, request=httpx.Request("GET", url))

    results = OnlineResearchProvider(request_get=fake_get).search("latest BTC market")

    assert len(results) == 1
    assert results[0].provider == "google_news_rss"
    assert results[0].publisher == "Example News"
    assert results[0].url.startswith("https://news.google.com/")


def test_online_query_redacts_personal_identifiers_and_rejects_secrets():
    safe = sanitize_online_query(
        "Research BTC for person@example.com wallet 0x1111111111111111111111111111111111111111"
    )

    assert "person@example.com" not in safe
    assert "0x1111" not in safe
    with pytest.raises(ProviderError, match="Sensitive content"):
        sanitize_online_query("search this api_key=secret-value")


def test_agent_uses_online_fallback_only_after_pipeline_has_no_documents(db, normal_user, monkeypatch):
    monkeypatch.setenv("AGENT_ONLINE_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("ONLINE_SEARCH_PROVIDER", "google_news")
    settings = Settings(enable_mock_agent=True, llm_provider="mock", agent_model="mock-model")
    monkeypatch.setattr(agent_service, "get_settings", lambda: settings)
    monkeypatch.setattr(agent_service, "get_agent_llm_provider", lambda selected_model=None: MockLLMProvider())

    fetched_at = datetime.now(timezone.utc)
    monkeypatch.setattr(
        OnlineResearchProvider,
        "search",
        lambda self, query, count=8: [
            OnlineResearchResult(
                provider="google_news_rss",
                publisher="Example News",
                title="Latest BTC source",
                snippet="Traceable public source metadata.",
                url="https://news.google.com/rss/articles/btc-example",
                published_at=fetched_at,
                fetched_at=fetched_at,
            )
        ],
    )
    conversation = agent_service.create_conversation(db, normal_user)
    run = agent_service.start_run(db, normal_user, conversation, "What is the latest BTC news?", context={})
    events = list(agent_service.stream_run(db, normal_user, run.id, "en"))

    calls = db.query(AgentToolCall).filter_by(run_id=run.id).order_by(AgentToolCall.created_at).all()
    online = next(call for call in calls if call.tool_name == "search_online_sources")
    citation = db.query(AgentMessageSource).filter_by(message_id=run.assistant_message_id).one()
    assert online.status == "completed"
    assert citation.provider == "google_news_rss"
    assert any('"tool": "search_online_sources"' in event for event in events)
    assert any('"sufficient": true' in event for event in events)


def test_online_tool_requires_rss_entitlement(db, normal_user, monkeypatch):
    monkeypatch.setenv("AGENT_ONLINE_RESEARCH_ENABLED", "true")
    registry = AgentToolRegistry(db, normal_user.id)
    registry.allowed_data_sources.clear()

    with pytest.raises(PermissionError, match="TOOL_ENTITLEMENT_DENIED"):
        registry.call("search_online_sources", {"query": "latest BTC news"})
