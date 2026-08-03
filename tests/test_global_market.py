from __future__ import annotations

from datetime import datetime, timezone

import pytest

from packages.data.global_market import build_global_snapshot
from packages.data.yahoo_provider import ASSET_TYPE_MAP, YahooFinanceProvider


def _fake_quote(provider: YahooFinanceProvider, symbol: str):
    from packages.data.base import MarketQuote

    price = {"AAPL": 300.0, "NVDA": 200.0, "MSFT": 100.0, "GC=F": 4100.0, "CL=F": 80.0, "EURUSD=X": 1.15}.get(symbol, 50.0)
    volume = {"AAPL": 132_000_000, "NVDA": 140_000_000, "MSFT": 60_000_000}.get(symbol, 10_000)
    return MarketQuote(
        symbol=symbol,
        price=price,
        volume_24h=volume * price,
        market_cap=0.0,
        funding_rate=0.0,
        open_interest=0.0,
        volatility=0.0,
        liquidation_estimate=0.0,
        sentiment_score=0.5,
        timestamp=datetime.now(timezone.utc),
        source=provider.provider_name,
        source_symbol=symbol,
        change_24h=1.5,
        is_realtime=False,
        asset_type=ASSET_TYPE_MAP.get(symbol, "equity"),
        open_interest_usd=None,
    )


class _FakeYahoo:
    provider_name = "yahoo_finance"

    def get_snapshot(self, symbols: list[str]):
        provider = YahooFinanceProvider()
        return [_fake_quote(provider, symbol) for symbol in symbols]


def test_global_snapshot_ranks_nasdaq_by_volume():
    payload = build_global_snapshot(nasdaq_top_n=3, provider=_FakeYahoo())
    assert payload["status"] == "HEALTHY"
    assert payload["order"] == ["nasdaq_top", "metals", "forex", "energy"]
    top = payload["groups"]["nasdaq_top"]
    # Ranked by dollar volume: AAPL 132M shares x 300 > NVDA 140M x 200 > MSFT
    assert [row["symbol"] for row in top] == ["AAPL", "NVDA", "MSFT"]
    assert len(top) == 3


def test_global_snapshot_contains_all_groups():
    payload = build_global_snapshot(nasdaq_top_n=5, provider=_FakeYahoo())
    assert payload["groups"]["metals"][0]["symbol"] == "GC=F"
    assert any(row["symbol"] == "CL=F" for row in payload["groups"]["energy"])
    assert any(row["symbol"] == "EURUSD=X" for row in payload["groups"]["forex"])
    for group in payload["groups"].values():
        assert all(row["price"] > 0 for row in group)


def test_yahoo_provider_parses_chart(monkeypatch):
    provider = YahooFinanceProvider()

    def fake_chart(symbol):
        return {
            "chart": {
                "result": [{
                    "meta": {
                        "regularMarketPrice": 308.91,
                        "chartPreviousClose": 300.0,
                        "regularMarketVolume": 132489137,
                        "regularMarketTime": 1754169600,
                    }
                }]
            }
        }

    monkeypatch.setattr(provider, "_chart", fake_chart)
    quote = provider.get_quote("AAPL")
    assert quote is not None
    assert quote.price == 308.91
    assert quote.change_24h == pytest.approx(2.97)
    assert quote.volume_24h > 0
    assert quote.asset_type == "equity"
    assert quote.is_realtime is False


def test_yahoo_provider_returns_none_on_failure(monkeypatch):
    provider = YahooFinanceProvider()

    def fail(symbol):
        raise RuntimeError("boom")

    monkeypatch.setattr(provider, "_chart", fail)
    assert provider.get_quote("AAPL") is None
