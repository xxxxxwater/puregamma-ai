from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apps.api.services.document_pipeline_service import persist_documents
from apps.api.services.data_source_service import data_capability
from packages.agents.chat.tools import AgentToolRegistry
from packages.data.provider import ProviderDocument
from packages.database.models import DataSource
from tests.conftest import auth_headers


def chaincatcher_item(external_id: str, title: str, published_at: datetime, *, language: str = "zh-CN", symbols=None) -> ProviderDocument:
    return ProviderDocument(
        external_id=external_id,
        source_name="ChainCatcher",
        source_type="flash_news",
        title=title,
        summary=f"Summary for {title}",
        url=f"https://www.chaincatcher.com/article/{external_id.rsplit('-', 1)[-1]}",
        published_at=published_at,
        language=language,
        symbols=symbols or [],
        topics=["market"],
        sentiment={"score": 0.1, "label": "neutral"},
        raw_payload={"content_type": "flash", "original": True, "keywords": ["market"]},
        license_status="linked-summary-only",
        redistribution_allowed=False,
    )


def test_news_feed_requires_auth_and_returns_attributed_flash(api_client, db, normal_user):
    now = datetime.now(timezone.utc)
    persist_documents(db, "chaincatcher", [chaincatcher_item("cc-1001", "BTC market update", now, symbols=["BTC"])])
    db.commit()

    assert api_client.get("/api/news").status_code == 401
    response = api_client.get(
        "/api/news?kind=flash&source=chaincatcher&language=zh&symbol=BTC",
        headers=auth_headers(normal_user),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["attribution"] == "ChainCatcher"
    assert payload["items"][0]["kind"] == "flash"
    assert payload["items"][0]["redistribution_allowed"] is False
    assert "content" not in payload["items"][0]
    assert response.headers["cache-control"].startswith("private")


def test_news_feed_cursor_filters_and_rss_entitlement_alias(api_client, db, normal_user):
    now = datetime.now(timezone.utc)
    items = [
        chaincatcher_item(f"cc-{index}", f"Update {index} ETH", now - timedelta(minutes=index), symbols=["ETH"])
        for index in range(1, 5)
    ]
    persist_documents(db, "chaincatcher", items)
    db.commit()

    first = api_client.get(
        "/api/news?kind=flash&source=chaincatcher&language=zh&q=ETH&limit=2",
        headers=auth_headers(normal_user),
    ).json()
    assert len(first["items"]) == 2
    assert first["page"]["has_more"] is True
    second = api_client.get(
        f"/api/news?kind=flash&source=chaincatcher&language=zh&q=ETH&limit=2&cursor={first['page']['next_cursor']}",
        headers=auth_headers(normal_user),
    ).json()
    assert {item["id"] for item in first["items"]}.isdisjoint({item["id"] for item in second["items"]})

    evidence = AgentToolRegistry(db, normal_user.id).search_source_documents(
        query="ETH update", providers=["rss"], symbols=["ETH"], hours=24
    )
    assert evidence.data
    assert evidence.data[0]["provider"] == "chaincatcher"


def test_english_feed_transparently_falls_back_during_rest_warmup(api_client, db, normal_user):
    now = datetime.now(timezone.utc)
    persist_documents(db, "chaincatcher", [chaincatcher_item("cc-2001", "中文 RSS 快讯", now)])
    db.commit()

    payload = api_client.get(
        "/api/news?kind=flash&source=chaincatcher&language=en",
        headers=auth_headers(normal_user),
    ).json()
    assert payload["meta"]["language"] == "en"
    assert payload["meta"]["language_fallback"] is True
    assert payload["items"][0]["language"] == "zh-CN"


def test_news_feed_rejects_user_without_rss_entitlement(api_client, normal_user, monkeypatch):
    monkeypatch.setattr(
        "apps.api.routers.news.get_user_entitlement",
        lambda db, user_id: {"allowed_data_sources": ["market"]},
    )
    response = api_client.get("/api/news", headers=auth_headers(normal_user))
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "NEWS_SOURCE_NOT_ENTITLED"


def test_chaincatcher_data_source_inherits_rss_plan_entitlement(db, normal_user):
    capability = data_capability(db, db.get(DataSource, "chaincatcher"), normal_user.id)
    assert capability["entitled"] is True
