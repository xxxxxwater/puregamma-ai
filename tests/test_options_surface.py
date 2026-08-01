from __future__ import annotations

import pytest

from datetime import datetime, timedelta, timezone

from packages.options.equity_options import EquityOptionsUnavailable, PolygonOptionsProvider
from packages.options.surface import build_surface, compute_atm_snapshot, days_to_expiry, resolve_surface_value


def _chain() -> dict:
    now = datetime.now(timezone.utc)
    instruments = []
    for dte, strike in [(10, 95), (10, 100), (10, 105), (30, 95), (30, 100), (30, 105)]:
        instruments.append(
            {
                "instrument": f"BTC-{dte}D-{strike}-C",
                "option_type": "call",
                "strike": float(strike),
                "expiry": (now + timedelta(days=dte)).isoformat(),
                "mark_iv": 45 + (strike - 100) * 0.2,
                "mark_price": 2.5,
                "underlying_price": 100.0,
                "volume_24h": 100,
                "open_interest": 500,
                "spread_pct": 0.02,
                "greeks": {"delta": 0.5, "gamma": 0.001, "theta": -5.0, "vega": 10.0},
            }
        )
    return {"status": "HEALTHY", "currency": "BTC", "instruments": instruments, "provider": "deribit_public"}


def test_build_surface_moneyness_and_dte():
    surface = build_surface(_chain(), "mark_iv")
    assert surface["underlying_price"] == 100.0
    assert len(surface["rows"]) == 6
    # moneyness = strike / underlying
    assert surface["rows"][0]["x"] == 0.95
    assert surface["rows"][1]["x"] == 1.0
    # DTE sorted ascending
    assert surface["rows"][0]["y"] == 10.0
    # Z matches mark_iv
    assert surface["rows"][1]["z"] == 45.0


def test_build_surface_greeks_type():
    surface = build_surface(_chain(), "gamma")
    assert all(row["z"] == 0.001 for row in surface["rows"])
    surface = build_surface(_chain(), "theta")
    assert all(row["z"] == -5.0 for row in surface["rows"])


def test_build_surface_skips_zero_strike():
    chain = _chain()
    chain["instruments"].append(
        {"instrument": "BAD", "strike": 0, "expiry": "2026-12-31T00:00:00+00:00", "mark_iv": 10}
    )
    surface = build_surface(chain, "mark_iv")
    assert len(surface["rows"]) == 6


def test_compute_atm_snapshot_skew():
    surface = build_surface(_chain(), "mark_iv")
    snapshot = compute_atm_snapshot(surface, dte_target=30, tolerance=5)
    assert snapshot["underlying_price"] == 100.0
    assert snapshot["atm_iv"] is not None
    assert snapshot["put25_iv"] is not None
    assert snapshot["call25_iv"] is not None
    # put (0.95) IV = 45 + (95-100)*0.2 = 44; call (1.05) IV = 46
    assert snapshot["put25_iv"] == 44.0
    assert snapshot["call25_iv"] == 46.0
    assert snapshot["skew_pct"] == -2.0


def test_days_to_expiry_parses_iso():
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    assert days_to_expiry(future) == pytest.approx(5.0)
    assert days_to_expiry("not-a-date") == 0.0


def test_resolve_surface_value_unknown_type_returns_none():
    instrument = {"mark_iv": 42.0}
    assert resolve_surface_value(instrument, "mark_iv") == 42.0
    assert resolve_surface_value(instrument, "unknown") is None


def test_polygon_provider_requires_api_key():
    provider = PolygonOptionsProvider("")
    try:
        provider.option_chain("AAPL")
    except EquityOptionsUnavailable as exc:
        assert "POLYGON_API_KEY" in str(exc)
        return
    raise AssertionError("expected EquityOptionsUnavailable without API key")


def test_polygon_provider_normalizes_chain(monkeypatch):
    provider = PolygonOptionsProvider("test-key")

    def fake_get(path, params):
        if "reference/options/contracts" in path:
            return [
                {
                    "ticker": "AAPL250815C00220000",
                    "underlying_ticker": "AAPL",
                    "contract_type": "call",
                    "strike_price": 220,
                    "expiration_date": "2025-08-15",
                    "shares_per_contract": 100,
                }
            ]
        return {
            "results": {
                "bid": 1.2,
                "ask": 1.4,
                "midpoint": 1.3,
                "implied_volatility": 0.35,
                "open_interest": 800,
                "day": {"volume": 1200},
                "underlying_asset": {"price": 218.5},
                "greek": {"delta": 0.48, "gamma": 0.002, "theta": -8.0, "vega": 12.0},
                "updated": "2025-08-01T12:00:00Z",
            }
        }

    monkeypatch.setattr(provider, "_get", fake_get)
    result = provider.option_chain("AAPL")
    assert result["status"] == "HEALTHY"
    assert result["currency"] == "AAPL"
    instrument = result["instruments"][0]
    assert instrument["strike"] == 220.0
    assert instrument["option_type"] == "call"
    assert instrument["mark_iv"] == 0.35
    assert instrument["greeks"]["gamma"] == 0.002
    assert instrument["open_interest"] == 800.0
    assert instrument["spread_pct"] > 0
