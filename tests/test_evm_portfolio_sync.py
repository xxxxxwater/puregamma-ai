from types import SimpleNamespace

from apps.api.services import portfolio_service


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_evm_sync_reads_active_chains_pages_and_usd_values(monkeypatch):
    calls = []
    saved = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params, headers, timeout))
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
        if params == {"chain": "eth", "limit": 100}:
            return FakeResponse(
                {
                    "cursor": "next-page",
                    "result": [
                        {
                            "symbol": "ETH",
                            "balance_formatted": "0.5",
                            "usd_price": 3000,
                            "usd_value": 1500,
                            "possible_spam": False,
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
        if params == {"chain": "eth", "limit": 100, "cursor": "next-page"}:
            return FakeResponse({"cursor": None, "result": []})
        if params == {"chain": "base", "limit": 100}:
            return FakeResponse(
                {
                    "cursor": None,
                    "result": [
                        {
                            "symbol": "USDC",
                            "balance_formatted": "125.25",
                            "usd_price": 1,
                            "usd_value": 125.25,
                            "possible_spam": False,
                        }
                    ],
                }
            )
        raise AssertionError(f"Unexpected Moralis request: {url} {params}")

    monkeypatch.setattr(
        portfolio_service,
        "get_settings",
        lambda: SimpleNamespace(
            moralis_api_key="test-key",
            moralis_api_url="https://deep-index.moralis.io/api/v2.2",
        ),
    )
    monkeypatch.setattr(
        portfolio_service,
        "_connection",
        lambda _db, _account: SimpleNamespace(
            metadata_json={"wallet_address": "0xabc", "chain_id": 1}
        ),
    )
    monkeypatch.setattr(portfolio_service.requests, "get", fake_get)
    monkeypatch.setattr(
        portfolio_service,
        "_save_snapshot",
        lambda _db, _account, equity, available, raw, positions, source: saved.update(
            {
                "equity": equity,
                "available": available,
                "raw": raw,
                "positions": positions,
                "source": source,
            }
        ),
    )

    portfolio_service._sync_evm(object(), object())

    assert saved["equity"] == 1625.25
    assert saved["available"] == 125.25
    assert saved["source"] == "evm"
    assert [item["symbol"] for item in saved["positions"]] == [
        "ETH @ eth",
        "USDC @ base",
    ]
    assert saved["positions"][0]["quantity"] == 0.5
    assert saved["raw"]["chain_errors"] == []
    assert len(calls) == 4
