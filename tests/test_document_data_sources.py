from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apps.api.services.document_pipeline_service import _ensure_circuit_available, aggregate_events, persist_documents, run_document_pipeline
from packages.agents.chat.tools import AgentToolRegistry
from packages.data.bloomberg_provider import BloombergProvider
from packages.data.enrichment import extract_symbols, weighted_sentiment
from packages.data.fintwit_provider import FinTwitAccountConfig, FinTwitProvider
from packages.data.provider import DataSourceStatus, ProviderDocument, ProviderError
from packages.data.rss_provider import RSSProvider, RSSSource
from packages.data.x_twitter_provider import XTwitterProvider
from packages.database.models import DataSource, NormalizedDocument, RawDocument
from tests.conftest import auth_headers


class FakeResponse:
    def __init__(self, payload=None, *, status_code=200, headers=None, content=b""):
        self._payload = payload or {}
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content
        self.is_redirect = False

    def json(self):
        return self._payload


def x_payload(next_token="next-page"):
    return {
        "data": [{"id": "100", "author_id": "42", "text": "BTC breakout gains momentum", "lang": "en", "created_at": "2026-07-10T00:00:00Z", "public_metrics": {"like_count": 50, "retweet_count": 4}}],
        "includes": {"users": [{"id": "42", "username": "analyst", "name": "Analyst"}]},
        "meta": {"next_token": next_token},
    }


def test_rss_xml_parse_dedup_symbols_topics(monkeypatch):
    source = RSSSource(id="test", name="Test RSS", url="https://news.example.com/feed")
    feed = b'<rss><channel><item><guid>1</guid><title>Bitcoin ETF inflow lifts BTC</title><link>https://news.example.com/a?utm_source=x</link><description>Market rally</description></item><item><guid>1</guid><title>Bitcoin ETF inflow lifts BTC</title><link>https://news.example.com/a</link><description>Market rally</description></item></channel></rss>'
    provider = RSSProvider(sources=[source])
    monkeypatch.setattr(provider, "_fetch", lambda _: feed)

    fetched = provider.fetch_latest()

    assert len(fetched.documents) == 1
    assert fetched.documents[0].symbols == ["BTC"]
    assert {"ETF", "market"}.issubset(fetched.documents[0].topics)
    assert fetched.documents[0].url == "https://news.example.com/a"


def test_rss_etag_and_last_modified_are_reused(monkeypatch):
    requests = []
    responses = [FakeResponse(headers={"etag": '"v1"', "last-modified": "Fri, 10 Jul 2026 00:00:00 GMT"}, content=b"<rss><channel /></rss>"), FakeResponse(status_code=304)]

    class Client:
        def __init__(self, **kwargs): self.headers = kwargs["headers"]
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def get(self, url):
            requests.append(self.headers)
            return responses.pop(0)

    monkeypatch.setattr("packages.data.rss_provider.httpx.Client", Client)
    source = RSSSource(id="etag", name="ETag", url="https://news.example.com/feed")
    provider = RSSProvider(sources=[source])
    assert provider._fetch(source)
    assert provider._fetch(source) is None
    assert requests[1]["If-None-Match"] == '"v1"'
    assert requests[1]["If-Modified-Since"] == "Fri, 10 Jul 2026 00:00:00 GMT"


def test_rss_retries_then_recovers(monkeypatch):
    attempts = {"count": 0}

    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def get(self, url):
            attempts["count"] += 1
            return FakeResponse(status_code=503 if attempts["count"] < 3 else 200, content=b"<rss><channel /></rss>")

    monkeypatch.setattr("packages.data.rss_provider.httpx.Client", Client)
    provider = RSSProvider(sources=[RSSSource(id="retry", name="Retry", url="https://news.example.com/feed")])
    assert provider._fetch(provider.sources[0])
    assert attempts["count"] == 3
    assert provider.get_usage().retries == 2


def test_fintwit_whitelist_rejects_non_whitelisted_author():
    account = FinTwitAccountConfig(username="allowed", display_name="Allowed", platform="x", category="quant researcher", provider_user_id="42")
    provider = FinTwitProvider(accounts=[account], x_provider=XTwitterProvider(bearer_token="token"))
    allowed = ProviderDocument(external_id="1", source_name="Allowed", source_type="social_opinion", title="BTC", author="allowed")
    denied = ProviderDocument(external_id="2", source_name="Unknown", source_type="social_opinion", title="BTC", author="spam")
    assert provider.normalize([allowed, denied]) == [allowed]


def test_x_without_key_reports_needs_key():
    provider = XTwitterProvider(bearer_token="")
    assert provider.health_check().status == DataSourceStatus.NEEDS_KEY
    with pytest.raises(ProviderError, match="X_BEARER_TOKEN"):
        provider.fetch_latest()


def test_x_pagination_and_rate_limit_headers():
    calls = []
    provider = XTwitterProvider(bearer_token="secret", request_get=lambda url, **kwargs: calls.append((url, kwargs)) or FakeResponse(x_payload(), headers={"x-rate-limit-limit": "100", "x-rate-limit-remaining": "77", "x-rate-limit-reset": "1783645200"}))
    result = provider.fetch_since("previous")
    assert calls[0][1]["params"]["pagination_token"] == "previous"
    assert result.next_cursor == "next-page"
    assert provider.get_usage().quota_remaining == 77
    assert result.documents[0].url == "https://x.com/analyst/status/100"


def test_x_rate_limit_raises_and_degrades():
    provider = XTwitterProvider(bearer_token="secret", request_get=lambda *args, **kwargs: FakeResponse(status_code=429, headers={"x-rate-limit-remaining": "0"}))
    with pytest.raises(ProviderError) as error:
        provider.fetch_latest()
    assert error.value.code == "rate_limited"
    assert provider.health_check().status == DataSourceStatus.DEGRADED


def test_bloomberg_requires_authorization_and_mock_is_explicit():
    unlicensed = BloombergProvider(mode="production", api_url="https://licensed.example.com/news", api_key="key", license_status="unlicensed")
    assert unlicensed.health_check().status == DataSourceStatus.LICENSE_REQUIRED
    missing_key = BloombergProvider(mode="production", api_url="https://licensed.example.com/news", api_key="", license_status="authorized")
    assert missing_key.health_check().status == DataSourceStatus.NEEDS_KEY
    mock = BloombergProvider(mode="mock", app_environment="development")
    assert mock.health_check().status == DataSourceStatus.MOCK
    assert mock.fetch_latest().documents[0].raw_payload["mock"] is True
    assert mock.fetch_latest().documents[0].content == ""


def test_bloomberg_mock_forbidden_in_production():
    assert BloombergProvider(mode="mock", app_environment="production").health_check().status == DataSourceStatus.ERROR


def test_symbol_recognition_and_weighted_score_bounds():
    assert extract_symbols("Solana and $BTC outperform while ETH is flat") == ["BTC", "ETH", "SOL"]
    assert weighted_sentiment(1, 0.9, 0.8, 0.7, 1) == pytest.approx(0.504)
    assert weighted_sentiment(4, 1, 1, 1, 1) == 1


def test_multi_source_event_aggregation_and_duplicate_guard(db):
    now = datetime.now(timezone.utc)
    first = ProviderDocument(external_id="rss-1", source_name="RSS One", source_type="rss_news", title="BTC ETF approval moves market", content="First report", url="https://one.example/a", published_at=now, symbols=["BTC"], topics=["ETF"], sentiment={"score": 0.5, "label": "positive"}, credibility_score=0.8)
    second = ProviderDocument(external_id="x-1", source_name="Analyst", source_type="social_opinion", title="BTC ETF approval moves market", content="Independent reaction", url="https://x.com/a/status/1", author="a", published_at=now, symbols=["BTC"], topics=["ETF"], sentiment={"score": 0.5, "label": "positive"}, credibility_score=0.6)
    assert persist_documents(db, "rss", [first]) == (1, 0)
    assert persist_documents(db, "x-twitter", [second]) == (1, 0)
    assert persist_documents(db, "rss", [first]) == (0, 1)
    db.commit()
    events = aggregate_events(db, symbol="BTC")
    assert len(events) == 1
    assert {item["provider"] for item in events[0]["sources"]} == {"rss", "x-twitter"}
    scores = [row.final_score for row in db.query(NormalizedDocument).order_by(NormalizedDocument.created_at).all()]
    assert scores[1] < scores[0]


def test_old_documents_do_not_reenter_recent_event_window(db):
    old = ProviderDocument(external_id="old", source_name="Old RSS", source_type="rss_news", title="Old BTC event", url="https://old.example/1", published_at=datetime.now(timezone.utc) - timedelta(days=10), symbols=["BTC"], sentiment={"score": 1, "label": "positive"})
    persist_documents(db, "rss", [old])
    row = db.query(NormalizedDocument).one()
    row.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    db.commit()
    assert aggregate_events(db, hours=24, symbol="BTC") == []


def test_circuit_open_and_forced_recovery():
    open_until = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    with pytest.raises(ProviderError) as error:
        _ensure_circuit_available({"circuitOpenUntil": open_until}, force=False)
    assert error.value.code == "circuit_open"
    _ensure_circuit_available({"circuitOpenUntil": open_until}, force=True)


def test_agent_retrieval_returns_source_citations(db, normal_user):
    item = ProviderDocument(external_id="agent-1", source_name="Research RSS", source_type="rss_news", title="SOL network upgrade supports market activity", summary="SOL technology update", url="https://research.example/sol", published_at=datetime.now(timezone.utc), symbols=["SOL"], topics=["technology"], sentiment={"score": 0.25, "label": "positive"}, credibility_score=0.8)
    persist_documents(db, "rss", [item])
    db.commit()
    result = AgentToolRegistry(db, normal_user.id).search_source_documents(query="SOL upgrade", symbols=["SOL"], hours=24)
    assert result.data[0]["evidenceType"] == "reported_fact"
    assert result.sources[0].url == "https://research.example/sol"
    assert result.sources[0].published_at is not None


def test_data_source_admin_apis_require_admin(api_client, normal_user, admin_user):
    assert api_client.get("/admin/data-sources", headers=auth_headers(normal_user)).status_code == 403
    response = api_client.get("/admin/data-sources", headers=auth_headers(admin_user))
    assert response.status_code == 200
    assert {item["id"] for item in response.json()["sources"]}.issuperset({"rss", "fintwit", "x-twitter", "bloomberg"})
    assert api_client.get("/admin/data-sources/rss/preview", headers=auth_headers(normal_user)).status_code == 403


def test_raw_and_normalized_documents_are_traceable(db):
    item = ProviderDocument(external_id="trace-1", source_name="Trace", source_type="rss_news", title="ETH market update", content="ETH liquidity improves", url="https://trace.example/eth", published_at=datetime.now(timezone.utc), symbols=["ETH"], sentiment={"score": 0.25, "label": "positive"})
    persist_documents(db, "rss", [item])
    db.commit()
    raw = db.query(RawDocument).one()
    normalized = db.query(NormalizedDocument).one()
    assert normalized.raw_document_id == raw.id
    assert normalized.url == raw.source_url


def test_four_provider_mock_transport_full_pipeline(db, monkeypatch):
    feed = b'<rss><channel><item><guid>rss-flow</guid><title>ETH market rally</title><link>https://flow.example/rss</link><description>ETH gains</description></item></channel></rss>'
    rss = RSSProvider(sources=[RSSSource(id="flow", name="Flow RSS", url="https://flow.example/feed")])
    monkeypatch.setattr(rss, "_fetch", lambda _: feed)
    x = XTwitterProvider(bearer_token="test-token", request_get=lambda *args, **kwargs: FakeResponse(x_payload(next_token=None)))
    fintwit_x = XTwitterProvider(bearer_token="test-token", request_get=lambda *args, **kwargs: FakeResponse(x_payload(next_token=None)))
    fintwit = FinTwitProvider(accounts=[FinTwitAccountConfig(username="analyst", display_name="Analyst", platform="x", category="quant researcher", provider_user_id="42")], x_provider=fintwit_x)
    bloomberg = BloombergProvider(mode="mock", app_environment="test")

    runs = [run_document_pipeline(db, db.get(DataSource, provider.id), provider, force=True) for provider in (rss, fintwit, x, bloomberg)]

    assert [run.status for run in runs] == ["HEALTHY", "HEALTHY", "HEALTHY", "MOCK"]
    assert db.query(NormalizedDocument).count() == 3
    assert sum(run.duplicate_count for run in runs) == 1
