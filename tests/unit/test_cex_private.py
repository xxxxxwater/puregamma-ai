"""Unit tests for the read-only private CEX adapters (P0-7).

Covers signature construction against recorded vectors, balance
normalization from recorded venue payloads, the dust filter, and the
no-secret invariant (secrets never appear in results, payloads, or logs).
"""

from __future__ import annotations

import json
import logging

import pytest

from packages.data.cex_private import (
    BinancePrivateAdapter,
    BybitPrivateAdapter,
    CexAdapterError,
    CexPermissionDenied,
    NormalizedHolding,
    OkxPrivateAdapter,
    adapter_for,
    filter_dust,
)

API_KEY = "test-api-key"
API_SECRET = "test-secret"
PASSPHRASE = "test-passphrase"

# Recorded vectors computed per venue documentation:
# Binance: hex(HMAC_SHA256("test-secret", "timestamp=1700000000000&recvWindow=5000"))
BINANCE_SIGNATURE = "3c006375c631729ab444c2afb86bee2999c35b6eeec838b8f96697e8f096d7b3"
# OKX: base64(HMAC_SHA256("test-secret", "2024-01-01T00:00:00.000Z" + "GET" + "/api/v5/account/balance"))
OKX_SIGNATURE = "a7mndkXijy+T0/hr8LSERYbJM1x53cAuRl/pI6BdFx4="
# Bybit: hex(HMAC_SHA256("test-secret", "1700000000000" + "test-api-key" + "5000" + "accountType=UNIFIED"))
BYBIT_SIGNATURE = "8be4249ab78e8b80892a552a4a5581635fdbcc0ada86289bbcd5ad9245477fd9"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode()

    def json(self):
        return self.payload


def _patch_transport(monkeypatch, handler):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {}), "timeout": timeout})
        return handler(url, params or {}, headers or {})

    monkeypatch.setattr("packages.data.cex_private.base.requests.get", fake_get)
    return calls


BINANCE_ACCOUNT = {
    "makerCommission": 10,
    "takerCommission": 10,
    "canTrade": False,
    "canWithdraw": False,
    "canDeposit": False,
    "accountType": "SPOT",
    "permissions": ["SPOT"],
    "balances": [
        {"asset": "BTC", "free": "0.50000000", "locked": "0.10000000"},
        {"asset": "USDT", "free": "1200.00000000", "locked": "0.00000000"},
        {"asset": "SHIB", "free": "9000.00000000", "locked": "0.00000000"},
        {"asset": "ETH", "free": "0.00000000", "locked": "0.00000000"},
    ],
}

OKX_BALANCE = {
    "code": "0",
    "msg": "",
    "data": [
        {
            "totalEq": "31400.00",
            "uTime": "1700000000000",
            "details": [
                {"availBal": "0.4", "cashBal": "0.4", "ccy": "BTC", "eq": "0.5", "eqUsd": "30000", "frozenBal": "0.1"},
                {"availBal": "1400", "cashBal": "1400", "ccy": "USDT", "eq": "1400", "eqUsd": "1400", "frozenBal": "0"},
                {"availBal": "25", "cashBal": "25", "ccy": "FOO", "eq": "25", "eqUsd": "", "frozenBal": "0"},
                {"availBal": "0", "cashBal": "0", "ccy": "DUST0", "eq": "0", "eqUsd": "0", "frozenBal": "0"},
            ],
        }
    ],
}

BYBIT_WALLET = {
    "retCode": 0,
    "retMsg": "OK",
    "result": {
        "list": [
            {
                "accountType": "UNIFIED",
                "coin": [
                    {"coin": "BTC", "walletBalance": "0.5", "usdValue": "30000", "locked": "0"},
                    {"coin": "USDC", "walletBalance": "800", "usdValue": "800", "locked": "0"},
                    {"coin": "BAR", "walletBalance": "42", "usdValue": "", "locked": "0"},
                    {"coin": "ETH", "walletBalance": "0", "usdValue": "0", "locked": "0"},
                ],
            }
        ]
    },
    "time": 1700000000000,
}

BYBIT_QUERY_API = {
    "retCode": 0,
    "retMsg": "OK",
    "result": {
        "apiKey": "test-api-key",
        "readOnly": 1,
        "permissions": {"ContractTrade": [], "Spot": [], "Wallet": [], "Options": [], "Derivatives": []},
        "ips": ["*"],
    },
    "time": 1700000000000,
}


def _binance_handler(url, params, headers):
    if url.endswith("/api/v3/account"):
        return FakeResponse(BINANCE_ACCOUNT)
    if url.endswith("/api/v3/ticker/price"):
        prices = {"BTCUSDT": "60000.00", "SHIBUSDT": "0.00001"}
        symbol = params.get("symbol")
        if symbol in prices:
            return FakeResponse({"symbol": symbol, "price": prices[symbol]})
        return FakeResponse({"code": -1121, "msg": "Invalid symbol."}, status_code=400)
    raise AssertionError(f"unexpected url {url}")


def _okx_handler(url, params, headers):
    if url.endswith("/api/v5/account/balance"):
        return FakeResponse(OKX_BALANCE)
    raise AssertionError(f"unexpected url {url}")


def _bybit_handler(url, params, headers):
    if "/v5/user/query-api" in url:
        return FakeResponse(BYBIT_QUERY_API)
    if "/v5/account/wallet-balance" in url:
        return FakeResponse(BYBIT_WALLET)
    raise AssertionError(f"unexpected url {url}")


# ---------------------------------------------------------------------------
# Signature construction (recorded vectors)
# ---------------------------------------------------------------------------


def test_binance_signature_matches_recorded_vector(monkeypatch):
    calls = _patch_transport(monkeypatch, _binance_handler)
    adapter = BinancePrivateAdapter()
    monkeypatch.setattr(adapter, "_timestamp_ms", lambda: 1700000000000)
    check = adapter.validate_credentials(API_KEY, API_SECRET)
    signed = next(call for call in calls if call["url"].endswith("/api/v3/account"))
    assert signed["params"]["signature"] == BINANCE_SIGNATURE
    assert signed["params"]["timestamp"] == 1700000000000
    assert signed["params"]["recvWindow"] == 5000
    assert signed["headers"]["X-MBX-APIKEY"] == API_KEY
    assert check.ok is True
    assert check.can_trade is False
    assert check.can_withdraw is False
    assert check.permissions_verified is True


def test_okx_signature_matches_recorded_vector(monkeypatch):
    calls = _patch_transport(monkeypatch, _okx_handler)
    adapter = OkxPrivateAdapter()
    monkeypatch.setattr(adapter, "_timestamp_iso", lambda: "2024-01-01T00:00:00.000Z")
    check = adapter.validate_credentials(API_KEY, API_SECRET, PASSPHRASE)
    signed = next(call for call in calls if call["url"].endswith("/api/v5/account/balance"))
    assert signed["headers"]["OK-ACCESS-SIGN"] == OKX_SIGNATURE
    assert signed["headers"]["OK-ACCESS-KEY"] == API_KEY
    assert signed["headers"]["OK-ACCESS-TIMESTAMP"] == "2024-01-01T00:00:00.000Z"
    assert signed["headers"]["OK-ACCESS-PASSPHRASE"] == PASSPHRASE
    assert check.ok is True
    # OKX main-account keys do not expose their own scopes on read endpoints.
    assert check.permissions_verified is False
    assert check.can_trade is None and check.can_withdraw is None
    assert check.metadata["assumed_read_only"] is True


def test_bybit_signature_matches_recorded_vector(monkeypatch):
    calls = _patch_transport(monkeypatch, _bybit_handler)
    adapter = BybitPrivateAdapter()
    monkeypatch.setattr(adapter, "_timestamp_ms", lambda: 1700000000000)
    check = adapter.validate_credentials(API_KEY, API_SECRET)
    adapter.fetch_balances(API_KEY, API_SECRET)
    signed = next(call for call in calls if "/v5/account/wallet-balance" in call["url"])
    assert signed["headers"]["X-BAPI-SIGN"] == BYBIT_SIGNATURE
    assert signed["headers"]["X-BAPI-API-KEY"] == API_KEY
    assert signed["headers"]["X-BAPI-TIMESTAMP"] == "1700000000000"
    assert signed["headers"]["X-BAPI-RECV-WINDOW"] == "5000"
    assert signed["headers"]["X-BAPI-SIGN-TYPE"] == "2"
    assert check.ok is True
    assert check.permissions_verified is True
    assert check.can_trade is False
    assert check.can_withdraw is False
    assert check.metadata["read_only"] is True


def test_bybit_permission_probe_flags_trade_and_withdraw_scopes(monkeypatch):
    payload = json.loads(json.dumps(BYBIT_QUERY_API))
    payload["result"]["readOnly"] = 0
    payload["result"]["permissions"] = {"ContractTrade": ["Order", "Position"], "Spot": ["SpotTrade"], "Wallet": ["AccountTransfer"]}
    _patch_transport(monkeypatch, lambda url, params, headers: FakeResponse(payload if "query-api" in url else BYBIT_WALLET))
    adapter = BybitPrivateAdapter()
    check = adapter.validate_credentials(API_KEY, API_SECRET)
    assert check.can_trade is True
    assert check.can_withdraw is True
    assert check.permissions_verified is True


def test_bybit_falls_back_to_unverified_when_query_api_unavailable(monkeypatch):
    def handler(url, params, headers):
        if "query-api" in url:
            return FakeResponse({"retCode": 10016, "retMsg": "error"}, status_code=200)
        return FakeResponse(BYBIT_WALLET)

    _patch_transport(monkeypatch, handler)
    adapter = BybitPrivateAdapter()
    check = adapter.validate_credentials(API_KEY, API_SECRET)
    assert check.ok is True
    assert check.permissions_verified is False
    assert check.metadata["assumed_read_only"] is True


# ---------------------------------------------------------------------------
# Balance normalization
# ---------------------------------------------------------------------------


def test_binance_fetch_balances_normalizes_and_prices(monkeypatch):
    _patch_transport(monkeypatch, _binance_handler)
    adapter = BinancePrivateAdapter()
    holdings = {item.symbol: item for item in adapter.fetch_balances(API_KEY, API_SECRET)}
    assert set(holdings) == {"BTC", "USDT", "SHIB"}
    assert holdings["BTC"].quantity == pytest.approx(0.6)
    assert holdings["BTC"].usd_value == pytest.approx(36000.0)
    assert holdings["USDT"].usd_value == pytest.approx(1200.0)
    assert holdings["SHIB"].usd_value == pytest.approx(0.09)
    # Zero balances are skipped; raw keeps venue fields without secrets.
    assert "ETH" not in holdings


def test_okx_fetch_balances_uses_venue_equsd(monkeypatch):
    _patch_transport(monkeypatch, _okx_handler)
    adapter = OkxPrivateAdapter()
    holdings = {item.symbol: item for item in adapter.fetch_balances(API_KEY, API_SECRET, PASSPHRASE)}
    assert set(holdings) == {"BTC", "USDT", "FOO"}
    assert holdings["BTC"].quantity == pytest.approx(0.5)
    assert holdings["BTC"].usd_value == pytest.approx(30000.0)
    assert holdings["USDT"].usd_value == pytest.approx(1400.0)
    # Empty eqUsd → unpriced (usd_value None), not zero.
    assert holdings["FOO"].usd_value is None
    assert holdings["FOO"].quantity == pytest.approx(25.0)


def test_bybit_fetch_balances_uses_venue_usdvalue(monkeypatch):
    _patch_transport(monkeypatch, _bybit_handler)
    adapter = BybitPrivateAdapter()
    holdings = {item.symbol: item for item in adapter.fetch_balances(API_KEY, API_SECRET)}
    assert set(holdings) == {"BTC", "USDC", "BAR"}
    assert holdings["BTC"].usd_value == pytest.approx(30000.0)
    assert holdings["USDC"].usd_value == pytest.approx(800.0)
    assert holdings["BAR"].usd_value is None


# ---------------------------------------------------------------------------
# Dust filter
# ---------------------------------------------------------------------------


def test_filter_dust_drops_sub_dollar_and_keeps_unpriced():
    holdings = [
        NormalizedHolding("BTC", 0.6, 36000.0, {}),
        NormalizedHolding("SHIB", 9000.0, 0.09, {}),
        NormalizedHolding("FOO", 25.0, None, {}),
    ]
    kept = filter_dust(holdings)
    assert [item.symbol for item in kept] == ["BTC", "FOO"]
    assert filter_dust([]) == []


# ---------------------------------------------------------------------------
# Errors and environments
# ---------------------------------------------------------------------------


def test_binance_auth_failure_maps_to_permission_denied(monkeypatch):
    _patch_transport(monkeypatch, lambda url, params, headers: FakeResponse({"code": -2015, "msg": "Invalid API-key"}, status_code=401))
    adapter = BinancePrivateAdapter()
    with pytest.raises(CexPermissionDenied):
        adapter.validate_credentials("bad-key", "bad-secret")


def test_okx_error_code_maps_to_permission_denied(monkeypatch):
    _patch_transport(monkeypatch, lambda url, params, headers: FakeResponse({"code": "50111", "msg": "Invalid OK-ACCESS-KEY", "data": []}))
    adapter = OkxPrivateAdapter()
    with pytest.raises(CexPermissionDenied):
        adapter.validate_credentials("bad-key", "bad-secret", "bad-pass")


def test_okx_requires_passphrase():
    adapter = OkxPrivateAdapter()
    with pytest.raises(CexPermissionDenied):
        adapter.validate_credentials(API_KEY, API_SECRET)


def test_bybit_retcode_maps_to_permission_denied(monkeypatch):
    _patch_transport(monkeypatch, lambda url, params, headers: FakeResponse({"retCode": 10003, "retMsg": "API key is invalid"}))
    adapter = BybitPrivateAdapter()
    with pytest.raises(CexPermissionDenied):
        adapter.validate_credentials("bad-key", "bad-secret")


def test_response_size_cap_is_enforced(monkeypatch):
    _patch_transport(monkeypatch, _binance_handler)
    adapter = BinancePrivateAdapter(max_response_bytes=16)
    with pytest.raises(CexAdapterError):
        adapter.validate_credentials(API_KEY, API_SECRET)


def test_testnet_environment_overrides():
    binance = adapter_for("binance", environment="testnet")
    assert binance.base_url == "https://testnet.binance.vision"
    bybit = adapter_for("bybit", environment="testnet")
    assert bybit.base_url == "https://api-testnet.bybit.com"
    okx = adapter_for("okx", environment="testnet")
    assert okx.base_url == "https://www.okx.com"  # demo trading via header
    assert okx.capability_notes == []


def test_okx_testnet_adds_simulated_trading_header(monkeypatch):
    calls = _patch_transport(monkeypatch, _okx_handler)
    adapter = OkxPrivateAdapter(environment="testnet")
    adapter.fetch_balances(API_KEY, API_SECRET, PASSPHRASE)
    assert calls[0]["headers"]["x-simulated-trading"] == "1"


def test_adapter_for_rejects_unknown_venue():
    with pytest.raises(ValueError):
        adapter_for("kraken")


# ---------------------------------------------------------------------------
# No-secret invariant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("adapter_cls", "handler", "kwargs"),
    [
        (BinancePrivateAdapter, _binance_handler, {}),
        (OkxPrivateAdapter, _okx_handler, {"passphrase": PASSPHRASE}),
        (BybitPrivateAdapter, _bybit_handler, {}),
    ],
)
def test_secrets_never_appear_in_results_payloads_or_logs(monkeypatch, caplog, adapter_cls, handler, kwargs):
    calls = _patch_transport(monkeypatch, handler)
    adapter = adapter_cls()
    passphrase = kwargs.get("passphrase")
    with caplog.at_level(logging.DEBUG):
        check = adapter.validate_credentials(API_KEY, API_SECRET, passphrase)
        holdings = adapter.fetch_balances(API_KEY, API_SECRET, passphrase)
    serialized = json.dumps({"check": check.metadata, "holdings": [item.raw for item in holdings]})
    assert API_SECRET not in serialized
    assert PASSPHRASE not in serialized
    for record in caplog.records:
        assert API_SECRET not in record.getMessage()
        assert PASSPHRASE not in record.getMessage()
    for call in calls:
        wire = json.dumps({"params": call["params"], "headers": call["headers"]})
        # The raw secret is never transmitted; only derived signatures are.
        assert API_SECRET not in wire
