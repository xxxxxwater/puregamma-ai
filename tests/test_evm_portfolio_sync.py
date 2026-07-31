from types import SimpleNamespace

import pytest

from apps.api.services import portfolio_service


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.payload}")

    def json(self):
        return self.payload


def _settings():
    return SimpleNamespace(
        moralis_api_key="test-key",
        moralis_api_url="https://deep-index.moralis.io/api/v2.2",
    )


def _connection():
    return SimpleNamespace(
        metadata_json={"wallet_address": "0xabc", "verified_chain_id": 1, "verification": "EIP-4361"}
    )


def _capture(saved):
    def _save(_db, _account, equity, available, raw, positions, source, daily_pnl=0.0):
        saved.update(
            {
                "equity": equity,
                "available": available,
                "raw": raw,
                "positions": positions,
                "source": source,
                "daily_pnl": daily_pnl,
            }
        )

    return _save


def _patch_common(monkeypatch, saved):
    monkeypatch.setattr(portfolio_service, "get_settings", _settings)
    monkeypatch.setattr(portfolio_service, "_connection", lambda _db, _account: _connection())
    monkeypatch.setattr(portfolio_service, "_save_snapshot", _capture(saved))


def test_evm_sync_reads_catalog_chains_pages_and_usd_values(monkeypatch):
    calls = []
    saved = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params))
        if url.endswith("/chains"):
            return FakeResponse(
                {
                    "active_chains": [
                        {"chain": "eth", "chain_id": "0x1"},
                        {"chain": "base", "chain_id": "0x2105"},
                        {"chain": "sepolia", "chain_id": "0xaa36a7"},
                    ]
                }
            )
        chain = (params or {}).get("chain")
        if chain == "eth" and "cursor" not in params:
            return FakeResponse(
                {
                    "cursor": "next-page",
                    "result": [
                        {
                            "symbol": "ETH",
                            "name": "Ether",
                            "balance_formatted": "0.5",
                            "usd_price": 3000,
                            "usd_value": 1500,
                            "usd_value_24hr_usd_change": -25.0,
                            "usd_price_24hr_percent_change": -1.64,
                            "possible_spam": False,
                            "native_token": True,
                            "verified_contract": True,
                        },
                        {
                            "symbol": "SCAM",
                            "balance_formatted": "999",
                            "usd_price": 1,
                            "usd_value": 999,
                            "possible_spam": True,
                        },
                    ],
                }
            )
        if chain == "eth" and params.get("cursor") == "next-page":
            return FakeResponse({"cursor": None, "result": []})
        if chain == "base":
            return FakeResponse(
                {
                    "cursor": None,
                    "result": [
                        {
                            "symbol": "USDC",
                            "name": "USD Coin",
                            "balance_formatted": "125.25",
                            "usd_price": 1,
                            "usd_value": 125.25,
                            "usd_value_24hr_usd_change": 0.01,
                            "possible_spam": False,
                            "verified_contract": True,
                        }
                    ],
                }
            )
        return FakeResponse({"cursor": None, "result": []})

    _patch_common(monkeypatch, saved)
    monkeypatch.setattr(portfolio_service.requests, "get", fake_get)

    portfolio_service._sync_evm(object(), object())

    assert saved["equity"] == 1625.25
    assert saved["available"] == 125.25
    assert saved["daily_pnl"] == pytest.approx(-24.99)
    assert saved["source"] == "evm"
    assert [item["symbol"] for item in saved["positions"]] == [
        "ETH @ eth",
        "USDC @ base",
    ]
    eth_position = saved["positions"][0]
    assert eth_position["quantity"] == 0.5
    assert eth_position["meta"]["chain"] == "eth"
    assert eth_position["meta"]["native"] is True
    assert eth_position["meta"]["change_24h"] == -25.0
    assert eth_position["meta"]["priced"] is True
    assert saved["raw"]["chain_errors"] == []
    assert {chain["chain"] for chain in saved["raw"]["chains"]} == {"eth", "base"}
    # Every catalog chain was queried with spam excluded server-side.
    token_calls = [params for url, params in calls if url.endswith("/tokens")]
    assert len(token_calls) >= len(portfolio_service._EVM_CHAIN_CATALOG)
    assert all(params.get("exclude_spam") == "true" for params in token_calls)
    # Testnet markers discovered via active-chain hints are skipped.
    assert all(params.get("chain") != "sepolia" for params in token_calls)


def test_evm_sync_falls_back_to_native_balance_when_tokens_endpoint_fails(monkeypatch):
    saved = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        if url.endswith("/chains"):
            return FakeResponse({"active_chains": [{"chain": "eth", "chain_id": "0x1"}]})
        if url.endswith("/tokens"):
            return FakeResponse({"message": "too many ERC20 token balances"}, status_code=400)
        if url.endswith("/balance"):
            chain = (params or {}).get("chain")
            wei = str(int(2 * 10**18)) if chain == "eth" else "0"
            return FakeResponse({"balance": wei})
        if "/erc20/" in url and url.endswith("/price"):
            return FakeResponse({"usdPrice": 3000.0, "24hrPercentChange": 2.5})
        raise AssertionError(f"Unexpected Moralis request: {url} {params}")

    _patch_common(monkeypatch, saved)
    monkeypatch.setattr(portfolio_service.requests, "get", fake_get)

    portfolio_service._sync_evm(object(), object())

    assert saved["equity"] == pytest.approx(6000.0)
    assert saved["daily_pnl"] == pytest.approx(150.0)
    assert len(saved["positions"]) == 1
    position = saved["positions"][0]
    assert position["symbol"] == "ETH @ eth"
    assert position["meta"]["fallback"] is True
    assert position["meta"]["native"] is True
    assert position["meta"]["change_24h_pct"] == pytest.approx(2.5)
    eth_errors = [item for item in saved["raw"]["chain_errors"] if item["chain"] == "eth"]
    assert eth_errors and eth_errors[0]["fallback"] == "native_balance"


def test_evm_sync_raises_when_all_chains_fail_without_fallback(monkeypatch):
    saved = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        if url.endswith("/chains"):
            return FakeResponse({"active_chains": []})
        return FakeResponse({"message": "upstream unavailable"}, status_code=500)

    _patch_common(monkeypatch, saved)
    monkeypatch.setattr(portfolio_service.requests, "get", fake_get)

    with pytest.raises(RuntimeError):
        portfolio_service._sync_evm(object(), object())
    assert saved == {}
