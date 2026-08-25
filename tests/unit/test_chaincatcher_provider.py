from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from packages.data.chaincatcher_provider import ChainCatcherProvider, _content_kind, _external_id, _normalize_language, _rss_category
from packages.data.provider import DataSourceStatus, ProviderError


class FakeResponse:
    def __init__(self, *, content: bytes = b"", payload=None, status_code: int = 200, headers=None):
        self.content = content
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.is_redirect = False

    def json(self):
        if self._payload is None:
            return json.loads(self.content)
        return self._payload


RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><item>
  <guid>https://www.chaincatcher.com/article/2285001</guid>
  <title><![CDATA[BTC ETF records fresh inflow]]></title>
  <link>https://www.chaincatcher.com/article/2285001?utm_source=rss</link>
  <description><![CDATA[BTC demand increased during the session.]]></description>
  <category>\xe5\xbf\xab\xe8\xae\xaf</category>
  <pubDate>Tue, 25 Aug 2026 04:15:52 +0100</pubDate>
</item></channel></rss>"""


def api_payload(language: str = "zh-CN") -> dict:
    title = "BTC ETF records fresh inflow" if language == "zh-CN" else "BTC ETF sees new inflows"
    url = "https://www.chaincatcher.com/article/2285001" if language == "zh-CN" else "https://www.chaincatcher.com/en/article/2285001"
    return {
        "result": 1,
        "message": "ok",
        "data": {
            "page": 1,
            "size": 100,
            "total": 1,
            "items": [{
                "id": 2285001,
                "type": "flash",
                "title": title,
                "digest": "BTC institutional demand increased.",
                "description": "This full field must not be retained as article content.",
                "content": "FULL ARTICLE BODY",
                "thumb": None,
                "url": url,
                "keywords": "BTC,ETF",
                "releaseTimeStamp": 1787627752000,
                "original": True,
            }],
        },
    }


def test_rss_and_rest_merge_by_language_and_article_id():
    calls: list[tuple[str, dict]] = []

    def request(url: str, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/rss/clist"):
            return FakeResponse(content=RSS)
        return FakeResponse(content=b"{}", payload=api_payload())

    now = datetime(2026, 8, 25, 4, 20, tzinfo=timezone.utc)
    provider = ChainCatcherProvider(languages=("zh-CN",), request_get=request, now=lambda: now)
    result = provider.fetch_since(None)

    assert len(result.documents) == 1
    document = result.documents[0]
    assert document.external_id == "chaincatcher:zh-CN:2285001"
    assert document.source_type == "flash_news"
    assert document.content == ""
    assert document.raw_payload["original"] is True
    assert document.raw_payload["keywords"] == ["BTC", "ETF"]
    assert document.raw_payload["ingestion_paths"] == ["rest", "rss"]
    assert "content" not in document.raw_payload
    assert "FULL ARTICLE BODY" not in json.dumps(document.raw_payload)
    assert json.loads(result.next_cursor or "{}")["restSyncedAt"] == now.isoformat()
    assert provider.health_check().status == DataSourceStatus.HEALTHY
    assert len(calls) == 2


def test_rest_refresh_is_throttled_but_fails_over_when_rss_breaks():
    now = datetime(2026, 8, 25, 4, 20, tzinfo=timezone.utc)
    calls: list[str] = []

    def healthy(url: str, **kwargs):
        calls.append(url)
        return FakeResponse(content=RSS) if url.endswith("/rss/clist") else FakeResponse(content=b"{}", payload=api_payload())

    provider = ChainCatcherProvider(languages=("zh-CN",), request_get=healthy, now=lambda: now)
    first = provider.fetch_since(None)
    calls.clear()
    second = provider.fetch_since(first.next_cursor)
    assert len(second.documents) == 1
    assert calls == ["https://www.chaincatcher.com/rss/clist"]

    def rss_down(url: str, **kwargs):
        calls.append(url)
        if url.endswith("/rss/clist"):
            return FakeResponse(status_code=503)
        return FakeResponse(content=b"{}", payload=api_payload())

    calls.clear()
    degraded = ChainCatcherProvider(languages=("zh-CN",), request_get=rss_down, now=lambda: now).fetch_since(first.next_cursor)
    assert degraded.documents
    assert degraded.errors and degraded.errors[0].startswith("rss:")


def test_rate_limit_is_explicit_and_never_retried():
    provider = ChainCatcherProvider(
        languages=("zh-CN",),
        request_get=lambda *args, **kwargs: FakeResponse(status_code=429, headers={"retry-after": "60"}),
    )
    with pytest.raises(ProviderError) as error:
        provider._request(provider.rss_url)
    assert error.value.code == "rate_limited"
    assert provider.get_usage().requests == 1
    assert provider.get_usage().rate_limit_reset_at is not None


def test_contract_normalization_prefers_url_id_and_accepts_real_rss_shapes():
    url = "https://www.chaincatcher.com/article/2285001"
    assert _external_id(url, "zh-CN", explicit_id=9999999) == "chaincatcher:zh-CN:2285001"
    assert _rss_category({"category": [{"term": "快讯"}]}) == "快讯"
    assert _rss_category({"tags": [{"term": "快报"}]}) == "快报"
    assert _content_kind("news-flash") == "flash"
    assert _content_kind("快訊") == "flash"
    assert _normalize_language("zh-cn") == "zh-CN"
    assert _normalize_language("en-US") == "en"
