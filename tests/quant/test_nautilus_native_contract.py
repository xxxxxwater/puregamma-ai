from __future__ import annotations

from packages.backtest.engine import BacktestEngine
from packages.nautilus.data_adapter import mock_catalog


def test_catalog_uses_native_external_perpetual_identifiers():
    catalog = mock_catalog(["BTC"], bar_count=4)

    assert catalog["instruments"][0]["id"] == "BTCUSDT-PERP.BINANCE"
    assert set(catalog["bars"]) == {
        "BTCUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL",
    }
    assert all(
        bar["bar_type"] == "BTCUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL"
        for bar in next(iter(catalog["bars"].values()))
    )


def test_missing_native_wheel_is_labeled_simulation(monkeypatch):
    monkeypatch.setattr("packages.backtest.engine._nautilus_available", lambda: False)

    result = BacktestEngine().run(
        "BTC replay",
        "BTC",
        {"lookback_days": 2},
        use_real_data=True,
    )

    assert result["engine"] == "puregamma_simulation_with_nautilus_catalog"
    assert result["mode"] == "mock"
    assert result["is_live"] is False
    assert result["bar_count"] == 48
