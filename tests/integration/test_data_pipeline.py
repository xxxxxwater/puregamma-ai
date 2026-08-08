from __future__ import annotations

import pytest

from apps.api.services.market_intelligence_service import generate_shared_market_intelligence
from packages.agents.sentiment_agent import SentimentAgent
from packages.data.mock_provider import MockMarketDataProvider
from packages.data.rss_provider import RSSProvider
from packages.data.x_provider import XProvider
from packages.data.bloomberg_provider import BloombergProvider
from packages.data.provider import DataSourceStatus


def test_coindesk_mock_provider_contract_with_market_mock():
    quotes = MockMarketDataProvider().get_snapshot(["BTC", "ETH"])

    assert [quote.symbol for quote in quotes] == ["BTC", "ETH"]
    assert all(quote.price > 0 for quote in quotes)


def test_rss_provider_returns_headlines(monkeypatch):
    feed = b'''<?xml version="1.0"?><rss version="2.0"><channel><title>Test</title><item><guid>btc-1</guid><title>BTC inflow growth</title><link>https://www.coindesk.com/test</link><description>Market update</description><pubDate>Fri, 10 Jul 2026 00:00:00 GMT</pubDate></item></channel></rss>'''
    monkeypatch.setattr(RSSProvider, "_fetch", lambda self, source: feed)
    headlines = RSSProvider().headlines()

    assert len(headlines) >= 1
    assert all(isinstance(item, str) for item in headlines)


def test_x_kol_mock_returns_posts_as_sentiment_scores():
    scores = XProvider().scan_sentiment(["BTC", "SOL"])

    assert scores == {"BTC": 0.5, "SOL": 0.5}


def test_sentiment_classifier_returns_valid_score():
    scores = SentimentAgent().aggregate(["BTC", "ETH", "SOL"])

    assert all(0 <= score <= 1 for score in scores.values())


def test_shared_market_intelligence_generated(db):
    intelligence = generate_shared_market_intelligence(db, ["BTC", "ETH"])

    assert intelligence.id
    assert intelligence.assets == ["BTC", "ETH"]


@pytest.mark.contract
def test_bloomberg_real_mode_disabled_without_credentials_contract():
    assert BloombergProvider(mode="production", api_url="", api_key="", license_status="unlicensed").health_check().status == DataSourceStatus.LICENSE_REQUIRED


@pytest.mark.contract
def test_data_source_status_updates_contract(db):
    from packages.database.models import DataSource
    assert db.get(DataSource, "rss").status in {"HEALTHY", "DISABLED", "ERROR", "DEGRADED"}


@pytest.mark.contract
def test_high_cost_source_requires_entitlement_contract(db):
    from apps.api.services.data_source_service import serialize_source
    from packages.database.models import DataSource
    assert serialize_source(db.get(DataSource, "x-twitter"))["requiredPlan"] == "Max"
    assert serialize_source(db.get(DataSource, "bloomberg"))["requiredPlan"] == "Max"


def test_data_capability_enforces_plan_and_reports_missing_freshness(db, normal_user):
    from apps.api.services.data_source_service import data_capability
    from packages.database.models import DataSource

    rss = data_capability(db, db.get(DataSource, "rss"), normal_user.id)
    x_twitter = data_capability(db, db.get(DataSource, "x-twitter"), normal_user.id)

    assert rss["entitled"] is True
    assert rss["stale"] is True
    assert rss["failure_reason"] in {"no_successful_sync", "provider_disabled"}
    assert x_twitter["entitled"] is False
    assert x_twitter["failure_reason"] == "plan_required"
    assert x_twitter["source_timestamp"] is None
