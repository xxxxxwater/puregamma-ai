from __future__ import annotations

import hashlib
import hmac
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

import httpx
import pytest


RUNTIME_ROOT = Path(__file__).parents[2] / "services" / "nautilus-runtime"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from adapters.binance_spot_testnet import (  # noqa: E402
    BinanceAPIError,
    BinanceSpotTestnetAdapter,
)
from adapters.hyperliquid import HyperliquidAdapter  # noqa: E402
from adapters.coinbase_advanced import CoinbaseAdvancedAdapter  # noqa: E402
from adapters.unavailable import UnavailableAdapter  # noqa: E402
from app.adapter_registry import adapter_for, adapter_key  # noqa: E402
from app.exchange_gateway import MockExchangeGateway  # noqa: E402


# --------------------------------------------------------------- registry


def test_registry_mock_account_keeps_mock_gateway():
    gateway = adapter_for({"venue": "MOCK", "environment": "paper"})
    assert isinstance(gateway, MockExchangeGateway)
    assert gateway.health_check()["adapter"] == "mock"


def test_registry_defaults_to_mock_when_account_missing():
    assert adapter_key(None) == ("MOCK", "paper")
    assert isinstance(adapter_for(None), MockExchangeGateway)


def test_registry_binance_testnet_selected():
    # Testnet order submission is fail-closed by default: without an explicit
    # NAUTILUS_TESTNET_SUBMIT_ENABLED=true (config.testnet_submit_enabled),
    # even a testnet venue resolves to the unavailable adapter.
    gateway = adapter_for(
        {"venue": "binance", "environment": "TESTNET"},
        config=None,
    )
    assert isinstance(gateway, UnavailableAdapter)

    class Config:
        testnet_submit_enabled = True
        binance_testnet_base_url = "https://testnet.binance.vision"
        binance_testnet_recv_window_ms = 5000
        binance_testnet_timeout_seconds = 10.0

    gateway = adapter_for(
        {"venue": "binance", "environment": "TESTNET"},
        config=Config(),
    )
    assert isinstance(gateway, BinanceSpotTestnetAdapter)
    assert gateway.base_url == "https://testnet.binance.vision"


def test_registry_hyperliquid_and_coinbase_selected():
    assert isinstance(
        adapter_for({"venue": "HYPERLIQUID", "environment": "paper"}),
        HyperliquidAdapter,
    )
    assert isinstance(
        adapter_for({"venue": "COINBASE_ADVANCED", "environment": "paper"}),
        CoinbaseAdvancedAdapter,
    )


def test_registry_unknown_venue_fails_closed():
    gateway = adapter_for({"venue": "KRAKEN", "environment": "paper"})
    assert isinstance(gateway, UnavailableAdapter)
    health = gateway.health_check()
    assert health["status"] == "UNAVAILABLE"
    assert "KRAKEN" in health["reason"]
    with pytest.raises(RuntimeError, match="unavailable"):
        gateway.submit_order({"client_order_id": "x"})
    with pytest.raises(RuntimeError, match="unavailable"):
        gateway.reconcile("acct")


def test_registry_live_environment_fails_closed_for_every_venue():
    for venue in ("BINANCE", "HYPERLIQUID", "MOCKLESS"):
        gateway = adapter_for({"venue": venue, "environment": "mainnet"})
        assert isinstance(gateway, UnavailableAdapter)
        assert "disabled" in gateway.health_check()["reason"]
        with pytest.raises(RuntimeError):
            gateway.submit_order({"client_order_id": "x"})


def test_registry_binance_non_testnet_environment_fails_closed():
    gateway = adapter_for({"venue": "BINANCE", "environment": "paper"})
    assert isinstance(gateway, UnavailableAdapter)
    # Status reads fail closed with an explicit UNAVAILABLE marker...
    assert gateway.fetch_account("acct")["status"] == "UNAVAILABLE"
    # ...while every order-path call raises with the reason.
    with pytest.raises(RuntimeError, match="unavailable"):
        gateway.submit_order({"client_order_id": "x"})
    with pytest.raises(RuntimeError, match="unavailable"):
        gateway.cancel_order("acct", "x")


# ---------------------------------------------------- binance testnet HTTP


def binance_adapter(handler) -> BinanceSpotTestnetAdapter:
    transport = httpx.MockTransport(handler)
    return BinanceSpotTestnetAdapter(
        api_key="test-key",
        api_secret="test-secret",
        base_url="https://testnet.binance.vision",
        transport=transport,
    )


def test_binance_signature_matches_official_vector():
    # Official Binance HMAC-SHA256 signing example.
    adapter = BinanceSpotTestnetAdapter(
        api_key="vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A",
        api_secret="NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j",
    )
    params = {
        "symbol": "LTCBTC",
        "side": "BUY",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": "1",
        "price": "0.1",
        "recvWindow": "5000",
        "timestamp": "1499827319559",
    }
    signed = adapter._sign(dict(params))
    assert (
        signed["signature"]
        == "c8db56825ae71d6d79447849e617115f4a920fa2acdcab2b053c4b2838bd6b71"
    )
    expected = hmac.new(
        b"NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j",
        urlencode(params).encode(),
        hashlib.sha256,
    ).hexdigest()
    assert signed["signature"] == expected


def test_binance_submit_market_order_maps_filled_ack():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = urlparse(str(request.url)).path
        seen["params"] = dict(parse_qsl(urlparse(str(request.url)).query))
        seen["api_key"] = request.headers.get("X-MBX-APIKEY")
        return httpx.Response(
            200,
            json={
                "symbol": "BTCUSDT",
                "orderId": 123456,
                "clientOrderId": "pg-test-1",
                "status": "FILLED",
                "executedQty": "0.01000000",
                "origQty": "0.01000000",
                "cummulativeQuoteQty": "600.00000000",
                "side": "BUY",
                "type": "MARKET",
                "price": "0.00000000",
            },
        )

    adapter = binance_adapter(handler)
    ack = adapter.submit_order(
        {
            "account_id": "acct-1",
            "client_order_id": "pg-test-1",
            "instrument": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.01,
        }
    )

    assert seen["path"] == "/api/v3/order"
    assert seen["api_key"] == "test-key"
    assert seen["params"]["newClientOrderId"] == "pg-test-1"
    assert seen["params"]["newOrderRespType"] == "FULL"
    assert seen["params"]["signature"]
    assert ack["state"] == "FILLED"
    assert ack["exchange_order_id"] == "123456"
    assert ack["filled_quantity"] == 0.01
    assert ack["average_price"] == 60000.0


def test_binance_submit_limit_order_maps_new_to_accepted():
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(parse_qsl(urlparse(str(request.url)).query))
        assert params["timeInForce"] == "GTC"
        assert params["price"] == "59000"
        return httpx.Response(
            200,
            json={
                "symbol": "BTCUSDT",
                "orderId": 77,
                "clientOrderId": "pg-limit-1",
                "status": "NEW",
                "executedQty": "0.00000000",
                "origQty": "0.01000000",
                "side": "BUY",
                "type": "LIMIT",
                "price": "59000.00000000",
            },
        )

    adapter = binance_adapter(handler)
    ack = adapter.submit_order(
        {
            "client_order_id": "pg-limit-1",
            "instrument": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 59000,
        }
    )
    assert ack["state"] == "ACCEPTED"
    assert ack["remaining_quantity"] == 0.01


def test_binance_business_error_maps_to_reject():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"code": -2010, "msg": "Account has insufficient balance for requested action."}
        )

    adapter = binance_adapter(handler)
    ack = adapter.submit_order(
        {
            "client_order_id": "pg-reject-1",
            "instrument": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 100,
        }
    )
    assert ack["state"] == "REJECTED"
    assert ack["error"] == "BINANCE_2010"
    assert "insufficient balance" in ack["error_detail"]


def test_binance_filter_failure_maps_to_reject():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": -1013, "msg": "Filter failure: MIN_NOTIONAL"})

    adapter = binance_adapter(handler)
    ack = adapter.submit_order(
        {
            "client_order_id": "pg-reject-2",
            "instrument": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.0000001,
        }
    )
    assert ack["state"] == "REJECTED"
    assert ack["error"] == "BINANCE_1013"


def test_binance_timestamp_error_syncs_and_retries_once():
    calls = {"order": 0, "time": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        if path == "/api/v3/time":
            calls["time"] += 1
            import time as _time

            return httpx.Response(200, json={"serverTime": int(_time.time() * 1000)})
        calls["order"] += 1
        if calls["order"] == 1:
            return httpx.Response(400, json={"code": -1021, "msg": "Timestamp for this request is outside of the recvWindow."})
        return httpx.Response(
            200,
            json={
                "symbol": "BTCUSDT",
                "orderId": 99,
                "clientOrderId": "pg-retry-1",
                "status": "NEW",
                "executedQty": "0",
                "origQty": "0.01",
                "side": "BUY",
                "type": "MARKET",
                "price": "0",
            },
        )

    adapter = binance_adapter(handler)
    ack = adapter.submit_order(
        {
            "client_order_id": "pg-retry-1",
            "instrument": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.01,
        }
    )
    assert ack["state"] == "ACCEPTED"
    assert calls == {"order": 2, "time": 1}


def test_binance_server_error_raises_for_unknown_state():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"code": -1000, "msg": "Internal error"})

    adapter = binance_adapter(handler)
    # -1000 is classified as a business reject (fail closed, no retry storm)
    ack = adapter.submit_order(
        {
            "client_order_id": "pg-err-1",
            "instrument": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.01,
        }
    )
    assert ack["state"] == "REJECTED"


def test_binance_transport_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    adapter = binance_adapter(handler)
    with pytest.raises(httpx.ConnectError):
        adapter.submit_order(
            {
                "client_order_id": "pg-net-1",
                "instrument": "BTCUSDT",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": 0.01,
            }
        )


def test_binance_missing_credentials_fail_before_any_request():
    adapter = BinanceSpotTestnetAdapter(api_key="", api_secret="")
    with pytest.raises(BinanceAPIError, match="credentials"):
        adapter.fetch_account("acct")


def test_binance_withdrawal_and_transfer_hard_fail():
    adapter = binance_adapter(lambda request: httpx.Response(200, json={}))
    with pytest.raises(RuntimeError, match="withdrawals are disabled"):
        adapter.withdraw(asset="USDT", amount=1, address="x")
    with pytest.raises(RuntimeError, match="transfers are disabled"):
        adapter.transfer(asset="USDT", amount=1)


def test_binance_health_and_order_book():
    def handler(request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        if path == "/api/v3/ping":
            return httpx.Response(200, json={})
        if path == "/api/v3/depth":
            return httpx.Response(
                200,
                json={
                    "bids": [["59900.0", "0.5"]],
                    "asks": [["60100.0", "0.4"], ["60200.0", "0.2"]],
                },
            )
        return httpx.Response(404, json={"code": -1, "msg": "not found"})

    adapter = binance_adapter(handler)
    health = adapter.health_check()
    assert health["status"] == "HEALTHY"
    assert health["live"] is False
    assert health["withdrawal"] is False and health["transfer"] is False
    book = adapter.fetch_order_book("BTCUSDT")
    assert book["asks"] == [[60100.0, 0.4], [60200.0, 0.2]]
    assert book["bids"] == [[59900.0, 0.5]]


def test_binance_cancel_and_fetch_order_roundtrip():
    store = {"status": "NEW"}

    def handler(request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        payload = {
            "symbol": "BTCUSDT",
            "orderId": 555,
            "clientOrderId": "pg-cancel-1",
            "status": store["status"],
            "executedQty": "0",
            "origQty": "0.01",
            "side": "BUY",
            "type": "LIMIT",
            "price": "59000",
        }
        if request.method == "DELETE":
            store["status"] = "CANCELED"
            payload["status"] = "CANCELED"
        return httpx.Response(200, json=payload)

    adapter = binance_adapter(handler)
    adapter._order_symbols["pg-cancel-1"] = "BTCUSDT"
    fetched = adapter.fetch_order("pg-cancel-1")
    assert fetched["state"] == "ACCEPTED"
    canceled = adapter.cancel_order("acct", "pg-cancel-1")
    assert canceled["state"] == "CANCELED"
    assert adapter.fetch_order("pg-unknown") is None
