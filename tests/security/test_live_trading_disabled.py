from __future__ import annotations

import os

import pytest


def test_live_trading_env_flags_default_to_disabled(monkeypatch):
    monkeypatch.delenv("NAUTILUS_LIVE_TRADING_ENABLED", raising=False)
    monkeypatch.delenv("NAUTILUS_ALLOW_LIVE_ORDER", raising=False)

    assert os.getenv("NAUTILUS_LIVE_TRADING_ENABLED", "false").lower() != "true"
    assert os.getenv("NAUTILUS_ALLOW_LIVE_ORDER", "false").lower() != "true"


@pytest.mark.contract
def test_submit_order_raises_live_trading_disabled_contract():
    pytest.xfail("No live trading/order submission service exists yet. Expected: submit_order raises LiveTradingDisabledError by default.")
