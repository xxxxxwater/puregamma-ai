from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.api.services import portfolio_service
from apps.api.services.billing_service import mock_upgrade
from apps.api.services.portfolio_service import connect_evm_wallet, portfolio_context, portfolio_view, sync_account


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.payload}")

    def json(self):
        return self.payload


def _moralis_settings():
    return SimpleNamespace(
        moralis_api_key="test-key",
        moralis_api_url="https://deep-index.moralis.io/api/v2.2",
        plaid_client_id="",
        plaid_secret="",
        plaid_env="sandbox",
        plaid_redirect_uri="",
    )


def _fake_moralis_get(url, params=None, headers=None, timeout=None):
    if url.endswith("/chains"):
        return FakeResponse({"active_chains": [{"chain": "eth", "chain_id": "0x1"}]})
    chain = (params or {}).get("chain")
    if url.endswith("/tokens") and chain == "eth":
        return FakeResponse(
            {
                "cursor": None,
                "result": [
                    {
                        "symbol": "ETH",
                        "name": "Ether",
                        "balance_formatted": "1.5",
                        "usd_price": 3000,
                        "usd_value": 4500,
                        "usd_value_24hr_usd_change": -50.0,
                        "usd_price_24hr_percent_change": -1.1,
                        "possible_spam": False,
                        "native_token": True,
                        "verified_contract": True,
                    },
                    {
                        "symbol": "USDC",
                        "name": "USD Coin",
                        "balance_formatted": "500",
                        "usd_price": 1,
                        "usd_value": 500,
                        "usd_value_24hr_usd_change": 0,
                        "usd_price_24hr_percent_change": 0,
                        "possible_spam": False,
                        "verified_contract": True,
                    },
                ],
            }
        )
    return FakeResponse({"cursor": None, "result": []})


@pytest.fixture()
def evm_portfolio(db, demo_user, monkeypatch):
    mock_upgrade(db, demo_user.id, "Max")
    monkeypatch.setattr("apps.api.services.portfolio_service.get_settings", _moralis_settings)
    monkeypatch.setattr("apps.api.services.portfolio_service.requests.get", _fake_moralis_get)
    account = connect_evm_wallet(db, demo_user, "0x" + "a" * 40, 1)
    sync_account(db, demo_user, account)
    return account


def test_portfolio_view_exposes_nav_holdings_and_daily_change(db, demo_user, evm_portfolio):
    result = portfolio_view(db, demo_user)

    assert result["connected"] is True
    assert result["nav"] == pytest.approx(5000.0)
    assert result["available_cash"] == pytest.approx(500.0)
    assert result["daily_change"] == pytest.approx(-50.0)
    assert result["daily_change_pct"] == pytest.approx(-50.0 / 5050.0 * 100, rel=1e-3)
    assert result["providers"]["evm"] is True

    holdings = {item["symbol"]: item for item in result["holdings"]}
    assert set(holdings) == {"ETH", "USDC"}
    eth = holdings["ETH"]
    assert eth["chain"] == "eth"
    assert eth["value"] == pytest.approx(4500.0)
    assert eth["weight"] == pytest.approx(0.9, rel=1e-3)
    assert eth["change_24h"] == pytest.approx(-50.0)
    assert eth["change_24h_pct"] == pytest.approx(-1.1)
    assert eth["asset_class"] == "crypto"
    assert eth["native"] is True
    assert eth["priced"] is True
    assert holdings["USDC"]["asset_class"] == "stablecoin"

    assert result["asset_classes"] == {"crypto": 4500.0, "stablecoin": 500.0}
    assert len(result["accounts"]) == 1
    account_row = result["accounts"][0]
    assert account_row["provider"] == "evm"
    assert account_row["nav"] == pytest.approx(5000.0)
    assert account_row["daily_change"] == pytest.approx(-50.0)
    assert account_row["as_of"] is not None


def test_portfolio_context_carries_asset_changes_for_agent(db, demo_user, evm_portfolio):
    context = portfolio_context(db, demo_user.id, detailed=True)

    assert context["connected"] is True
    assert context["total_nav"] == pytest.approx(5000.0)
    assert context["daily_change"] == pytest.approx(-50.0)
    assert context["daily_change_pct"] == pytest.approx(-50.0 / 5050.0 * 100, rel=1e-3)
    assert context["holding_count"] == 2
    assert context["asset_classes"] == {"crypto": 4500.0, "stablecoin": 500.0}
    assert len(context["accounts"]) == 1
    assert context["accounts"][0]["provider"] == "evm"

    holdings = {item["symbol"]: item for item in context["top_holdings"]}
    assert holdings["ETH"]["chain"] == "eth"
    assert holdings["ETH"]["change_24h"] == pytest.approx(-50.0)
    assert holdings["ETH"]["asset_class"] == "crypto"
    assert holdings["ETH"]["price"] == pytest.approx(3000.0)
    assert holdings["USDC"]["asset_class"] == "stablecoin"
