from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import httpx

from apps.api.services.daily_brief_service import _local_brief, _trending_providers, gather_context
from apps.api.services.market_intelligence_service import DEFAULT_ASSETS
from packages.data.binance_provider import BinanceProvider
from packages.data.earnings_calendar import upcoming_earnings
from packages.data.hyperliquid_provider import HyperliquidProvider
from packages.data.public_market_provider import PublicMarketDataProvider
from packages.data.trending import top_trending
from packages.database.models import (
    EntityMention,
    MarketSnapshot,
    NormalizedDocument,
    RawDocument,
    SharedMarketIntelligence,
    Source,
    utcnow,
)
from packages.reports.unified_daily_brief import MAX_IMESSAGE_BYTES, generate_unified_daily_brief


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _fake_httpx_get(url, params=None, timeout=None, headers=None):
    symbol = (params or {}).get("symbol", "BTCUSDT")
    if url.endswith("/api/v3/ticker/24hr"):
        return _FakeResponse({"lastPrice": "66008.01", "priceChangePercent": "0.8", "quoteVolume": "1234567", "closeTime": 1784715778000})
    if url.endswith("/fapi/v1/premiumIndex"):
        return _FakeResponse({"symbol": symbol, "markPrice": "65933.9", "lastFundingRate": "0.00003888"})
    if url.endswith("/fapi/v1/openInterest"):
        return _FakeResponse({"symbol": symbol, "openInterest": "103130.936"})
    raise AssertionError(url)


def test_binance_quote_includes_funding_rate_and_open_interest(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_httpx_get)
    quote = BinanceProvider().get_quote("BTC")
    assert quote.price == 66008.01
    assert quote.funding_rate == 0.00003888
    assert quote.open_interest == 103130.936
    assert quote.open_interest_usd == round(103130.936 * 65933.9, 2)


def test_binance_quote_survives_futures_outage(monkeypatch):
    def broken(url, params=None, timeout=None, headers=None):
        if url.endswith("/api/v3/ticker/24hr"):
            return _FakeResponse({"lastPrice": "66008.01", "priceChangePercent": "0.8", "quoteVolume": "1234567", "closeTime": 1784715778000})
        raise httpx.ConnectError("futures down")

    monkeypatch.setattr(httpx, "get", broken)
    quote = BinanceProvider().get_quote("BTC")
    assert quote.price == 66008.01
    assert quote.funding_rate == 0.0
    assert quote.open_interest == 0.0


def test_upcoming_earnings_week_view():
    items = upcoming_earnings(date(2026, 7, 21), days=7, locale="en")
    joined = "; ".join(items)
    assert "GOOGL" in joined and "07-21" in joined
    assert "TSLA" in joined and "07-22" in joined
    assert "(est.)" in joined
    zh_items = upcoming_earnings(date(2026, 7, 21), days=7, locale="zh")
    assert "（预计）" in "; ".join(zh_items)
    assert upcoming_earnings(date(2026, 3, 3), days=7, locale="en") == []


def _seed_document(db, symbol: str, title: str, age_hours: float = 1.0, provider: str = "rss") -> None:
    source = db.query(Source).filter_by(provider=provider, external_key="test-feed").one_or_none()
    if not source:
        source = Source(provider=provider, provider_type="news", external_key="test-feed", name="Test Feed")
        db.add(source)
        db.flush()
    created = utcnow() - timedelta(hours=age_hours)
    raw = RawDocument(
        source_id=source.id,
        provider=provider,
        external_id=f"{provider}-{symbol}-{title}-{age_hours}",
        content_hash=f"{provider}-{symbol}-{title}-{age_hours}",
        raw_payload={},
        processing_status="normalized",
    )
    db.add(raw)
    db.flush()
    doc = NormalizedDocument(
        raw_document_id=raw.id,
        source_id=source.id,
        provider=provider,
        source_type="news",
        source_name="Test Feed",
        title=title,
        content="",
        summary="",
        published_at=created,
        language="en",
        symbols=[symbol],
        stable_hash=f"stable-{provider}-{symbol}-{title}-{age_hours}",
        event_fingerprint=f"fp-{provider}-{symbol}-{title}-{age_hours}",
        created_at=created,
    )
    db.add(doc)
    db.flush()
    db.add(EntityMention(document_id=doc.id, symbol=symbol, mention_text=symbol, created_at=created))


def test_top_trending_ranks_mentions(db):
    for index in range(3):
        _seed_document(db, "NVDA", f"NVDA story {index}")
    for index in range(2):
        _seed_document(db, "TSLA", f"TSLA story {index}")
    _seed_document(db, "BTC", "BTC story")
    _seed_document(db, "AAPL", "Old AAPL story", age_hours=72)
    db.commit()

    items = top_trending(db, hours=24, limit=5)

    assert [item["symbol"] for item in items] == ["NVDA", "TSLA", "BTC"]
    assert items[0]["mentions"] == 3
    assert items[0]["sample_title"].startswith("NVDA story")
    assert all(item["symbol"] != "AAPL" for item in items)
    assert top_trending(db, hours=24, limit=2)[0]["symbol"] == "NVDA"


def test_gather_context_exposes_earnings_and_trending(db, demo_user):
    snapshot = MarketSnapshot(asset_id="BTC", price=66008.01, volume_24h=1e9, market_cap=0, funding_rate=0.0001, open_interest=1000, timestamp=utcnow())
    db.add(snapshot)
    db.flush()
    db.add(
        SharedMarketIntelligence(
            market_regime="neutral",
            summary_markdown="x",
            assets=["BTC"],
            source_snapshot_ids=[snapshot.id],
        )
    )
    _seed_document(db, "NVDA", "NVDA story")
    db.commit()

    context = gather_context(db, demo_user.id, "en")

    assert context["market_stale"] is False
    assert any("NVDA" == item["symbol"] for item in context["trending_symbols"])
    assert isinstance(context["upcoming_earnings"], list)


def test_local_brief_renders_new_sections():
    context = {
        "market_regime": "neutral",
        "market_data_as_of": datetime.now(timezone.utc).isoformat(),
        "market_stale": False,
        "quotes": [{"symbol": "BTC", "price": 66008.01}],
        "upcoming_earnings": ["TSLA 07-22 earnings (est.)"],
        "trending_symbols": [{"symbol": "NVDA", "mentions": 3, "sample_title": "NVDA story"}],
        "portfolio": {"connected": False, "top_holdings": [], "stale": False, "missing_data": [], "total_nav": 0, "daily_change": 0, "concentration_hhi": 0},
    }
    zh = _local_brief(context, "zh", "")
    en = _local_brief(context, "en", "")
    assert "今日全网热议" in zh and "NVDA" in zh
    assert "美股财报（未来一周）" in zh and "TSLA" in zh
    assert "Trending today" in en and "NVDA" in en
    assert "US earnings this week" in en and "TSLA" in en


def test_unified_brief_includes_trending_and_week_earnings(db):
    db.add(MarketSnapshot(asset_id="BTC", price=66008.01, volume_24h=1e9, market_cap=0, funding_rate=0.0001, open_interest=1000, timestamp=utcnow()))
    db.add(SharedMarketIntelligence(market_regime="neutral", summary_markdown="x", source_snapshot_ids=[]))
    _seed_document(db, "NVDA", "NVDA story")
    db.commit()

    brief = generate_unified_daily_brief(db, "zh", today=date(2026, 7, 21))

    assert "美股财报(7天)" in brief and "GOOGL" in brief
    assert "热议" in brief and "NVDA" in brief
    assert len(brief.encode("utf-8")) <= MAX_IMESSAGE_BYTES


def _hyperliquid_payload(*coins: str):
    universe = [{"name": coin} for coin in coins]
    contexts = [
        {
            "funding": "0.00001234",
            "openInterest": "15234.5",
            "markPx": "59.42",
            "dayNtlVlm": "12345678.9",
        }
        for _ in coins
    ]
    return [{"universe": universe}, contexts]


def test_hyperliquid_quote_parses_perp_context(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: _FakeResponse(_hyperliquid_payload("HYPE")))
    quote = HyperliquidProvider().get_quote("HYPE")
    assert quote.source == "hyperliquid"
    assert quote.price == 59.42
    assert quote.funding_rate == 0.00001234
    assert quote.open_interest == 15234.5
    assert quote.open_interest_usd == round(15234.5 * 59.42, 2)


def test_hyperliquid_missing_symbol_raises(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: _FakeResponse(_hyperliquid_payload("HYPE")))
    provider = HyperliquidProvider()
    try:
        provider.get_quote("DOGE")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown perp")


class _StubQuoteProvider:
    provider_name = "stub"

    def get_quote(self, symbol: str):
        if symbol != "HYPE":
            raise ValueError(symbol)
        from packages.data.base import MarketQuote

        return MarketQuote(
            symbol="HYPE",
            price=59.17,
            volume_24h=1e6,
            market_cap=0.0,
            funding_rate=0.0,
            open_interest=0.0,
            volatility=0.0,
            liquidation_estimate=0.0,
            sentiment_score=0.0,
            timestamp=datetime.now(timezone.utc),
            source="coinbase",
            is_realtime=True,
        )


def test_public_provider_enriches_crypto_quote_with_hyperliquid(monkeypatch):
    provider = PublicMarketDataProvider(providers=[_StubQuoteProvider()], mode="auto")
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: _FakeResponse(_hyperliquid_payload("HYPE")))

    quotes = provider.get_snapshot(["HYPE"])

    assert len(quotes) == 1
    assert quotes[0].price == 59.17  # spot price source is preserved
    assert quotes[0].funding_rate == 0.00001234
    assert quotes[0].open_interest == 15234.5
    assert quotes[0].open_interest_usd == round(15234.5 * 59.42, 2)


def test_public_provider_survives_hyperliquid_outage(monkeypatch):
    provider = PublicMarketDataProvider(providers=[_StubQuoteProvider()], mode="auto")

    def broken(*args, **kwargs):
        raise httpx.ConnectError("hyperliquid down")

    monkeypatch.setattr(httpx, "post", broken)
    quotes = provider.get_snapshot(["HYPE"])
    assert quotes[0].funding_rate == 0.0
    assert quotes[0].open_interest == 0.0


def test_top_trending_provider_filter(db):
    _seed_document(db, "BTC", "RSS BTC story", provider="rss")
    for index in range(3):
        _seed_document(db, "SOL", f"X SOL story {index}", provider="x-twitter")
    db.commit()

    rss_only = top_trending(db, hours=24, limit=5, providers=("rss",))
    assert [item["symbol"] for item in rss_only] == ["BTC"]

    everything = top_trending(db, hours=24, limit=5, providers=("rss", "x-twitter"))
    assert everything[0]["symbol"] == "SOL" and everything[0]["mentions"] == 3

    assert top_trending(db, hours=24, limit=5, providers=()) == []


def test_trending_providers_from_entitlement():
    assert _trending_providers({"market", "rss", "portfolio"}) == ("rss",)
    assert _trending_providers({"market", "rss", "fintwit", "portfolio"}) == ("rss", "fintwit")
    assert _trending_providers({"rss", "x"}) == ("rss", "x-twitter")
    assert _trending_providers({"rss", "x-twitter"}) == ("rss", "x-twitter")
    assert _trending_providers({"all"}) == ("rss", "fintwit", "x-twitter")
    assert _trending_providers(set()) == ()


def test_default_assets_exclude_equities_without_keys():
    assert "MSTR" not in DEFAULT_ASSETS
    assert "STRC" not in DEFAULT_ASSETS
    assert {"BTC", "ETH", "HYPE"} <= set(DEFAULT_ASSETS)


def test_gather_context_free_plan_excludes_x_twitter_buzz(db, demo_user):
    snapshot = MarketSnapshot(asset_id="BTC", price=66008.01, volume_24h=1e9, market_cap=0, funding_rate=0.0001, open_interest=1000, timestamp=utcnow())
    db.add(snapshot)
    db.flush()
    db.add(
        SharedMarketIntelligence(
            market_regime="neutral",
            summary_markdown="x",
            assets=["BTC"],
            source_snapshot_ids=[snapshot.id],
        )
    )
    _seed_document(db, "SOL", "X SOL story", provider="x-twitter")
    db.commit()

    context = gather_context(db, demo_user.id, "en")

    assert all(item["symbol"] != "SOL" for item in context["trending_symbols"])
    assert context["quotes"][0]["open_interest_usd"] == round(1000 * 66008.01, 2)
