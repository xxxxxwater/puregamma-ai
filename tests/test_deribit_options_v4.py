from __future__ import annotations

from datetime import datetime, timedelta, timezone

from packages.options.deribit import DeribitPublicProvider
from packages.options.long_gamma import discover_long_gamma


def test_deribit_option_chain_normalizes_and_enriches(monkeypatch):
    future = int((datetime.now(timezone.utc) + timedelta(days=20)).timestamp() * 1000)
    provider = DeribitPublicProvider("https://www.deribit.com")

    def fake_get(method, params):
        if method.endswith("get_instruments"):
            return [
                {
                    "instrument_name": "BTC-TEST-60000-C",
                    "base_currency": "BTC",
                    "option_type": "call",
                    "strike": 60000,
                    "expiration_timestamp": future,
                    "contract_size": 1,
                    "min_trade_amount": 0.1,
                }
            ]
        if method.endswith("get_book_summary_by_currency"):
            return [
                {
                    "instrument_name": "BTC-TEST-60000-C",
                    "bid_price": 0.05,
                    "ask_price": 0.06,
                    "mid_price": 0.055,
                    "mark_price": 0.054,
                    "mark_iv": 52,
                    "underlying_price": 61000,
                    "volume": 100,
                    "open_interest": 500,
                }
            ]
        return {
            "greeks": {"delta": 0.52, "gamma": 0.0002, "theta": -12, "vega": 30},
            "mark_iv": 52,
            "index_price": 61000,
            "timestamp": future,
        }

    monkeypatch.setattr(provider, "_get", fake_get)
    result = provider.option_chain("BTC", detail_limit=1)

    assert result["status"] == "HEALTHY"
    assert result["live_trading"] is False
    assert result["instruments"][0]["greeks"]["gamma"] == 0.0002
    assert result["instruments"][0]["spread_pct"] > 0


def test_long_gamma_discovery_requires_real_greeks():
    expiry = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    complete = {
        "instrument": "BTC-X-C",
        "expiry": expiry,
        "volume_24h": 300,
        "open_interest": 1000,
        "spread_pct": 0.05,
        "greeks": {"gamma": 0.002, "theta": -0.1},
    }
    incomplete = {**complete, "instrument": "BTC-Y-P", "greeks": {}}

    result = discover_long_gamma([incomplete, complete])

    assert [row["instrument"] for row in result] == ["BTC-X-C"]
    assert result[0]["research_score"] > 0
    assert result[0]["execution_enabled"] is False


def test_options_api_is_public_read_only(api_client, monkeypatch):
    monkeypatch.setattr(
        "apps.api.routers.options.get_option_chain",
        lambda currency: {
            "provider": "deribit_public",
            "status": "HEALTHY",
            "currency": currency,
            "instruments": [],
            "live_trading": False,
        },
    )
    response = api_client.get("/options/chain?currency=BTC")

    assert response.status_code == 200
    assert response.json()["live_trading"] is False
