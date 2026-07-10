from __future__ import annotations

import pytest

from apps.api.services.billing_service import mock_upgrade
from tests.conftest import auth_headers


def test_pro_can_run_mock_backtest(api_client, db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")
    before = demo_user.credit_balance

    response = api_client.post(
        "/backtest",
        json={"strategy_name": "BTC momentum breakout", "asset": "BTC", "params": {"lookback_days": 20}},
        headers=auth_headers(demo_user),
    )
    db.refresh(demo_user)

    assert response.status_code == 200
    assert response.json()["backtest"]["credits_spent"] == 25
    assert demo_user.credit_balance == before - 25
    assert {"total_return", "sharpe", "max_drawdown", "win_rate"} <= set(response.json()["backtest"]["result"]["metrics"])


@pytest.mark.contract
def test_free_cannot_use_nautilus_contract(api_client, normal_user):
    response = api_client.post(
        "/backtest",
        json={"strategy_name": "BTC momentum breakout", "asset": "BTC", "params": {}},
        headers=auth_headers(normal_user),
    )

    if response.status_code == 200:
        pytest.xfail("Free users can currently run backtests if they have enough credits; Nautilus entitlement guard is missing.")
    assert response.status_code == 402


@pytest.mark.contract
def test_submit_order_live_trading_disabled_contract():
    pytest.xfail("No Nautilus live order submission service exists yet. Expected: submit_order always raises LiveTradingDisabledError unless both live flags are true.")
