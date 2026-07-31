"""Unit tests for the unified research fact & event impact engine (P0-1)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from apps.api.services import research_event_service
from packages.data import earnings_calendar
from packages.data.earnings_calendar import ProviderUnavailable
from packages.database.models import (
    AccountSnapshot,
    AssetImpact,
    ExchangeConnection,
    MarketEvent,
    MarketQuoteRecord,
    MarketSnapshot,
    NormalizedDocument,
    PositionSnapshot,
    RawDocument,
    ResearchAction,
    Source,
    TradingAccount,
    UserPortfolioImpact,
    utcnow,
)


@pytest.fixture(autouse=True)
def offline_providers(monkeypatch):
    """Keep every external provider offline for the unit suite."""
    monkeypatch.setattr(research_event_service, "_fetch_deribit_metrics", lambda: None)
    monkeypatch.setattr(
        earnings_calendar, "upcoming_confirmed_earnings", lambda start_day, days=7: []
    )


def _quote(symbol: str, base: str, pct: float | None, *, age_minutes: float = 5) -> MarketQuoteRecord:
    now = utcnow()
    return MarketQuoteRecord(
        symbol=symbol,
        base_asset=base,
        quote_asset="USDT",
        asset_type="spot",
        provider="binance",
        price=100.0,
        change_24h_pct=pct,
        source_timestamp=now - timedelta(minutes=age_minutes),
        fetched_at=now - timedelta(minutes=age_minutes),
        provenance_json={"provider": "binance", "source_url": "https://api.binance.com/api/v3/ticker/24hr"},
    )


def _snapshot(asset: str, price: float, *, age_minutes: float) -> MarketSnapshot:
    return MarketSnapshot(
        asset_id=asset,
        price=price,
        volume_24h=1_000_000.0,
        timestamp=utcnow() - timedelta(minutes=age_minutes),
    )


def _news_document(db, *, title: str, symbols: list[str], final_score: float = 0.8) -> NormalizedDocument:
    source = Source(
        provider="rss",
        provider_type="rss",
        external_key="unit-test-feed",
        name="Unit Test Feed",
        source_url="https://example.com/feed",
    )
    db.add(source)
    db.flush()
    raw = RawDocument(
        source_id=source.id,
        provider="rss",
        external_id=f"ext-{title}",
        content_hash=f"hash-{title}",
        raw_payload={"title": title, "link": "https://example.com/article-1"},
        published_at=utcnow() - timedelta(hours=1),
    )
    db.add(raw)
    db.flush()
    doc = NormalizedDocument(
        raw_document_id=raw.id,
        source_id=source.id,
        provider="rss",
        source_type="news",
        source_name="Unit Test Feed",
        title=title,
        content="Stored article body used by the research engine.",
        summary="Stored article summary.",
        url="https://example.com/article-1",
        published_at=utcnow() - timedelta(hours=1),
        symbols=symbols,
        stable_hash=f"stable-{title}",
        event_fingerprint=f"fp-{title}",
        final_score=final_score,
    )
    db.add(doc)
    db.commit()
    return doc


def test_build_is_rerun_safe_via_fingerprint_dedup(db):
    db.add(_quote("BTCUSDT", "BTC", 7.5))
    _news_document(db, title="Bitcoin rallies on stored test news", symbols=["BTC"])
    db.commit()

    first = research_event_service.build_research_events(db, "intraday", 24)
    count_after_first = db.query(MarketEvent).count()
    assert count_after_first > 0
    assert sum(first.source_counts_json.values()) == count_after_first

    second = research_event_service.build_research_events(db, "intraday", 24)
    assert db.query(MarketEvent).count() == count_after_first
    assert second.source_counts_json == {}
    # Fingerprints stay unique across runs.
    fingerprints = [row[0] for row in db.query(MarketEvent.fingerprint).all()]
    assert len(fingerprints) == len(set(fingerprints))


def test_price_move_threshold_and_confidence_tiers(db):
    db.add(_quote("BTCUSDT", "BTC", 7.5))  # fresh, above threshold
    db.add(_quote("ETHUSDT", "ETH", 2.0))  # below threshold
    db.add(_quote("SOLUSDT", "SOL", -8.2, age_minutes=180))  # stale, above threshold
    db.add(_snapshot("HYPE", 40.0, age_minutes=10))  # single snapshot: no pair
    db.add(_snapshot("DOGE", 0.10, age_minutes=30))
    db.add(_snapshot("DOGE", 0.1065, age_minutes=5))  # +6.5% from snapshot pair
    db.commit()

    snapshot = research_event_service.build_research_events(db, "intraday", 24)
    events = {
        (event.event_type, tuple(event.assets)): event
        for event in db.query(MarketEvent).filter(MarketEvent.event_type == "price_move").all()
    }
    assert ("price_move", ("BTC",)) in events
    assert ("price_move", ("SOL",)) in events
    assert ("price_move", ("DOGE",)) in events
    assert ("price_move", ("ETH",)) not in events
    assert ("price_move", ("HYPE",)) not in events

    assert events[("price_move", ("BTC",))].direction == "up"
    assert events[("price_move", ("BTC",))].confidence == pytest.approx(0.9)  # fresh < 30min
    assert events[("price_move", ("SOL",))].direction == "down"
    assert events[("price_move", ("SOL",))].confidence == pytest.approx(0.6)  # stale
    assert snapshot.health_json["price_move"]["status"] == "ok"

    result = research_event_service.compute_asset_impacts(db, snapshot)
    assert result["created"] > 0
    btc_impact = (
        db.query(AssetImpact)
        .filter(AssetImpact.event_id == events[("price_move", ("BTC",))].id, AssetImpact.symbol == "BTC")
        .one()
    )
    assert btc_impact.relation_type == "direct"
    assert btc_impact.direction == "up"
    assert btc_impact.magnitude == pytest.approx(7.5)
    # Rerun-safe: no duplicate impact rows.
    assert research_event_service.compute_asset_impacts(db, snapshot)["created"] == 0


_RECORDED_NASDAQ = {
    "data": {
        "rows": [
            {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "time": "time-after-hours",
                "epsForecast": "$1.42",
                "marketCap": "$3.2T",
                "asOf": "2026-07-24",
            },
            {
                "symbol": "TSLA",
                "name": "Tesla, Inc.",
                "time": "time-pre-market",
                "epsForecast": "$0.39",
                "marketCap": "$980B",
                "asOf": "2026-07-24",
            },
            {"symbol": "", "name": "Row without symbol", "time": None},
        ]
    }
}


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload
        self.content = json.dumps(payload).encode()

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeSession:
    def __init__(self, payload: dict | Exception):
        self._payload = payload
        self.calls: list[dict] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if isinstance(self._payload, Exception):
            raise self._payload
        return _FakeResponse(self._payload)


def test_earnings_parser_on_recorded_nasdaq_json():
    day = datetime(2026, 7, 24, tzinfo=timezone.utc).date()
    rows = earnings_calendar.parse_nasdaq_earnings(_RECORDED_NASDAQ, day)
    assert [row["symbol"] for row in rows] == ["AAPL", "TSLA"]
    apple = rows[0]
    assert apple["name"] == "Apple Inc."
    assert apple["time_label"] == "time-after-hours"
    assert apple["eps_forecast"] == "$1.42"
    assert apple["market_cap"] == "$3.2T"
    assert apple["as_of"] == "2026-07-24"
    assert apple["confirmed"] is True
    assert apple["source_url"] == earnings_calendar.NASDAQ_EARNINGS_PAGE_URL

    assert earnings_calendar.parse_nasdaq_earnings({"data": {"rows": None}}, day) == []
    with pytest.raises(ProviderUnavailable):
        earnings_calendar.parse_nasdaq_earnings({"unexpected": True}, day)


def test_fetch_confirmed_earnings_via_session_and_failure(monkeypatch):
    # Avoid any real Redis dependency inside the provider cache layer.
    monkeypatch.setattr(earnings_calendar, "_cache_read", lambda day: None)
    monkeypatch.setattr(earnings_calendar, "_cache_write", lambda day, rows: None)
    day = datetime(2026, 7, 24, tzinfo=timezone.utc).date()

    session = _FakeSession(_RECORDED_NASDAQ)
    rows = earnings_calendar.fetch_confirmed_earnings(day, session=session)
    assert [row["symbol"] for row in rows] == ["AAPL", "TSLA"]
    assert session.calls[0]["params"] == {"date": "2026-07-24"}
    assert session.calls[0]["headers"]["User-Agent"] == "Mozilla/5.0"

    failing = _FakeSession(httpx.ConnectError("boom"))
    with pytest.raises(ProviderUnavailable):
        earnings_calendar.fetch_confirmed_earnings(day, session=failing)


def _synthetic_holdings(db, user) -> None:
    captured = utcnow()
    account = TradingAccount(
        user_id=user.id,
        name="Synthetic Hyperliquid",
        venue="HYPERLIQUID",
        account_type="READ_ONLY",
        base_currency="USD",
        status="ACTIVE",
        permissions_json={"read_positions": True},
    )
    db.add(account)
    db.flush()
    db.add(
        ExchangeConnection(
            user_id=user.id,
            account_id=account.id,
            adapter="hyperliquid",
            environment="production",
            status="CONNECTED",
            metadata_json={"wallet_address": "0x" + "a" * 40},
        )
    )
    db.add(
        AccountSnapshot(
            user_id=user.id,
            account_id=account.id,
            balance=10_000.0,
            equity=10_000.0,
            available_margin=5_000.0,
            daily_pnl=0.0,
            drawdown=0.0,
            exposure=5_000.0,
            stale=False,
            raw_event_reference={"provider": "hyperliquid", "payload": {}},
            captured_at=captured,
        )
    )
    db.add(
        PositionSnapshot(
            user_id=user.id,
            account_id=account.id,
            instrument="BTC",
            quantity=0.1,
            side="LONG",
            average_price=45_000.0,
            mark_price=50_000.0,
            unrealized_pnl=500.0,
            realized_pnl=0.0,
            leverage=1.0,
            raw_event_reference={"provider": "hyperliquid", "value": 5_000.0},
            captured_at=captured,
        )
    )
    db.commit()


def test_user_portfolio_impacts_and_actions_with_synthetic_holdings(db, demo_user):
    _synthetic_holdings(db, demo_user)
    db.add(_quote("BTCUSDT", "BTC", 7.5))
    db.commit()

    snapshot = research_event_service.build_research_events(db, "intraday", 24)
    research_event_service.compute_asset_impacts(db, snapshot)
    result = research_event_service.compute_user_portfolio_impacts(db, snapshot)
    assert result["created"] >= 1

    btc_event = (
        db.query(MarketEvent)
        .filter(MarketEvent.event_type == "price_move", MarketEvent.research_snapshot_id == snapshot.id)
        .one()
    )
    impact = (
        db.query(UserPortfolioImpact)
        .filter(
            UserPortfolioImpact.user_id == demo_user.id,
            UserPortfolioImpact.event_id == btc_event.id,
            UserPortfolioImpact.symbol == "BTC",
        )
        .one()
    )
    assert impact.exposure_value == pytest.approx(5_000.0)
    assert impact.exposure_weight == pytest.approx(0.5)
    assert impact.direction == "up"

    actions = db.query(ResearchAction).filter(ResearchAction.user_id == demo_user.id).all()
    assert actions
    assert all(action.action_type in {"ask_agent", "add_alert", "generate_report"} for action in actions)
    assert any(event.title in (action.payload_json or {}).get("prompt", "") for action in actions for event in [btc_event])
    dedup_keys = [action.dedup_key for action in db.query(ResearchAction).all()]
    assert len(dedup_keys) == len(set(dedup_keys))

    # Rerun-safe: no duplicate impacts or actions.
    rerun = research_event_service.compute_user_portfolio_impacts(db, snapshot)
    assert rerun["created"] == 0
    assert rerun["actions"] == 0


def test_provider_failure_marks_health_and_creates_no_earnings_events(db, monkeypatch):
    def _raise(start_day, days=7):
        raise ProviderUnavailable("nasdaq earnings calendar unavailable")

    monkeypatch.setattr(earnings_calendar, "upcoming_confirmed_earnings", _raise)
    snapshot = research_event_service.build_research_events(db, "intraday", 24)

    assert snapshot.health_json["earnings_confirmed"]["status"] == "unavailable"
    assert "nasdaq" in snapshot.health_json["earnings_confirmed"]["error"]
    assert db.query(MarketEvent).filter(MarketEvent.event_type == "earnings_confirmed").count() == 0

    upcoming = research_event_service.get_upcoming_events(db, days=14)
    assert all(event["event_type"] != "earnings_confirmed" for event in upcoming["events"])

    today = research_event_service.get_today(db, _any_user(db), "en")
    assert today["health"]["overall"] == "degraded"


def _any_user(db):
    from packages.database.models import User as _User

    return db.query(_User).first()
