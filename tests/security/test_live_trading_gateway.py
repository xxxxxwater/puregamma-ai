"""Real execution gateway (Binance spot) tests.

Uses an httpx.MockTransport standing in for the Binance REST API so no test
ever requires a real venue or credentials. Covers the launch-critical safety
properties from docs/live-trading/PROMPT_MVP_LIVE_BACKEND.md:

- submit timeout -> order UNKNOWN, submitted exactly once, never retried;
- Binance business rejections -> REJECTED ack (no retry ambiguity);
- unsafe API-key permissions (withdraw/transfer/leverage/futures/options) ->
  health reports permissions.safe=False, connection hard-rejected + ops alert;
- HMAC signing + order/fill/balance/position mapping;
- an end-to-end approved-user small-order flow (preview -> confirm -> sync ->
  fill -> immutable ledger -> NAV) with no plaintext secrets anywhere;
- the honest mock gateway DISABLED semantics;
- reconciliation against real gateway balances (ok + error -> pause).
"""

from __future__ import annotations

import json
import time
from decimal import Decimal

import httpx
import pytest
from cryptography.fernet import Fernet

from packages.database.models import (
    BrokerConnection,
    Fill,
    LedgerEntry,
    LiveOrder,
    LiveUserApproval,
    StrategyRelease,
    TradingAccount,
    TradingMandate,
    TradingStrategy,
)
from packages.live_trading import control_plane, flags, ledger, nav
from packages.live_trading import price_feed as price_feed_service
from packages.live_trading import reconciliation as reconciliation_service
from packages.live_trading import secret_store
from packages.live_trading.binance_spot_gateway import BinanceSpotLiveGateway
from packages.live_trading.gateway_adapter import (
    GatewayOrderUnknown,
    GatewayUnavailable,
    MockExecutionGateway,
)

CREDENTIALS = {"api_key": "test-api-key", "api_secret": "test-api-secret-value"}


# ---------------------------------------------------------------------------
# Binance mock server (httpx.MockTransport handler)
# ---------------------------------------------------------------------------


class BinanceMockServer:
    """Stateful Binance REST stand-in with per-path error/timeout injection."""

    def __init__(
        self,
        *,
        order_status: str = "NEW",
        query_status: str | None = None,
        query_filled: bool = False,
        balance_free: str = "1000",
        balance_locked: str = "0",
        restrictions: dict | None = None,
        trades: list[dict] | None = None,
        ticker: dict[str, str] | None = None,
        error_paths: dict[tuple[str, str], tuple[int, dict]] | None = None,
        timeout_paths: set[tuple[str, str]] | None = None,
    ):
        self.order_status = order_status
        self.query_status = query_status or order_status
        self.query_filled = query_filled
        self.balance_free = balance_free
        self.balance_locked = balance_locked
        self.restrictions = restrictions or {
            "enableWithdrawals": False,
            "enableInternalTransfer": False,
            "permitsUniversalTransfer": False,
            "enableVanillaOptions": False,
            "enableFutures": False,
            "enableMargin": False,
            "enableSpotAndMarginTrading": True,
            "enableReading": True,
        }
        self.trades = trades or []
        self.ticker = ticker or {"BTCUSDT": "100"}
        self.error_paths = error_paths or {}
        self.timeout_paths = timeout_paths or set()
        self.calls: dict[tuple[str, str], int] = {}
        self.last_order_params: dict = {}

    def _order_payload(self, request: httpx.Request, *, query: bool = False) -> dict:
        params = request.url.params
        if query and self.query_filled:
            executed = "0.5"
            quote_qty = "50"
            status = "FILLED"
        elif query:
            executed = "0"
            quote_qty = "0"
            status = self.query_status
        else:
            executed = "0"
            quote_qty = "0"
            status = self.order_status
        return {
            "symbol": params.get("symbol", "BTCUSDT"),
            "orderId": 123456,
            "clientOrderId": params.get("newClientOrderId") or params.get("origClientOrderId") or "pg-unknown",
            "orderListId": -1,
            "transactTime": int(time.time() * 1000),
            "price": "0",
            "origQty": params.get("quantity", "0.5"),
            "executedQty": executed,
            "cummulativeQuoteQty": quote_qty,
            "status": status,
            "timeInForce": "GTC",
            "type": params.get("type", "MARKET"),
            "side": params.get("side", "BUY"),
            "stopPrice": "0",
            "icebergQty": "0",
            "updateTime": int(time.time() * 1000),
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        self.calls[key] = self.calls.get(key, 0) + 1
        if key in self.timeout_paths:
            raise httpx.ReadTimeout("binance timed out", request=request)
        if key in self.error_paths:
            status, body = self.error_paths[key]
            return httpx.Response(status, json=body, request=request)

        path = request.url.path
        if path == "/api/v3/ping":
            return httpx.Response(200, json={}, request=request)
        if path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": int(time.time() * 1000)}, request=request)
        if path == "/sapi/v1/account/apiRestrictions":
            return httpx.Response(200, json=self.restrictions, request=request)
        if path == "/api/v3/account":
            return httpx.Response(
                200,
                json={
                    "canTrade": True,
                    "balances": [
                        {"asset": "USDT", "free": self.balance_free, "locked": self.balance_locked},
                        {"asset": "BTC", "free": "0.5", "locked": "0"},
                        {"asset": "BNB", "free": "1", "locked": "0"},
                    ],
                },
                request=request,
            )
        if path == "/api/v3/order" and request.method == "POST":
            params = dict(request.url.params)
            self.last_order_params = params
            if not params.get("signature"):
                return httpx.Response(
                    400, json={"code": -1022, "msg": "Signature required"}, request=request
                )
            return httpx.Response(200, json=self._order_payload(request), request=request)
        if path == "/api/v3/order" and request.method == "GET":
            return httpx.Response(
                200, json=self._order_payload(request, query=True), request=request
            )
        if path == "/api/v3/order" and request.method == "DELETE":
            payload = self._order_payload(request)
            payload["status"] = "CANCELED"
            return httpx.Response(200, json=payload, request=request)
        if path == "/api/v3/myTrades":
            return httpx.Response(200, json=self.trades, request=request)
        if path == "/api/v3/ticker/price":
            symbols = request.url.params.get("symbols")
            if symbols:
                payload = [
                    {"symbol": symbol, "price": self.ticker.get(symbol, "0")}
                    for symbol in json.loads(symbols)
                ]
            else:
                payload = [
                    {"symbol": symbol, "price": price}
                    for symbol, price in self.ticker.items()
                ]
            return httpx.Response(200, json=payload, request=request)
        return httpx.Response(404, json={"code": -9999, "msg": f"unhandled path {path}"}, request=request)


def make_gateway(server: BinanceMockServer, **kwargs) -> BinanceSpotLiveGateway:
    return BinanceSpotLiveGateway(
        transport=httpx.MockTransport(server.handler),
        credential_resolver=lambda connection_id: CREDENTIALS,
        timeout=kwargs.pop("timeout", 2.0),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Test world (approved LIVE stack, mirrors test_live_trading_foundation.py)
# ---------------------------------------------------------------------------


def _enable_static_gate(monkeypatch):
    gate = flags.GateResult(enabled=True, checks={})
    monkeypatch.setattr(flags, "evaluate_static_gate", lambda: gate)


def _make_live_world(db, user, monkeypatch, **mandate_kwargs):
    test_key = Fernet.generate_key()
    monkeypatch.setattr(secret_store, "_fernet", lambda: Fernet(test_key))
    _enable_static_gate(monkeypatch)
    account = TradingAccount(
        user_id=user.id,
        name="live-account",
        venue="BINANCE",
        account_type="LIVE",
        base_currency="USD",
        status="ACTIVE",
    )
    db.add(account)
    db.flush()

    strategy = TradingStrategy(
        user_id=user.id,
        name="live-strategy",
        description="",
        status="ACTIVE",
        execution_mode="LIVE",
    )
    db.add(strategy)
    db.flush()

    release = StrategyRelease(
        user_id=user.id,
        strategy_id=strategy.id,
        strategy_version=1,
        release_number=1,
        spec_json={"entry": "n/a"},
        spec_hash="sha256:test",
        review_status="approved",
        created_by="user",
    )
    db.add(release)
    db.flush()

    connection = BrokerConnection(
        user_id=user.id,
        provider="binance_spot",
        account_label="main",
        encrypted_credentials_ref=secret_store.encrypt_secrets(CREDENTIALS),
        environment="production",
        status="HEALTHY",
    )
    db.add(connection)
    db.flush()

    defaults = dict(
        user_id=user.id,
        account_id=account.id,
        strategy_release_id=release.id,
        broker_connection_id=connection.id,
        execution_mode="live",
        environment="production",
        status="active",
        allowed_symbols_json=["BTCUSDT"],
        allowed_side="both",
        max_total_notional=Decimal("10000"),
        max_per_order_notional=Decimal("2000"),
        max_position_notional=Decimal("5000"),
        max_leverage=Decimal("1"),
        max_daily_loss=Decimal("500"),
        max_trades_per_day=10,
        max_order_frequency_seconds=0,
        kill_switch_state="inactive",
        paused=False,
        approval_status="approved",
        idempotency_key=f"mandate:{user.id}:gateway-test",
    )
    defaults.update(mandate_kwargs)
    mandate = TradingMandate(**defaults)
    db.add(mandate)
    db.flush()

    approval = LiveUserApproval(
        user_id=user.id,
        status="approved",
        max_total_notional=Decimal("10000"),
    )
    db.add(approval)
    db.commit()
    price_feed_service.record_price(db, symbol="BTCUSDT", price="100", venue="MOCK")
    db.commit()
    return {
        "account": account,
        "connection": connection,
        "mandate": mandate,
    }


# ---------------------------------------------------------------------------
# Timeout -> UNKNOWN, exactly once, never retried
# ---------------------------------------------------------------------------


def test_submit_timeout_becomes_unknown_and_never_retries(db, user_factory, monkeypatch):
    user = user_factory("timeout@test.com")
    world = _make_live_world(db, user, monkeypatch)
    server = BinanceMockServer(timeout_paths={("POST", "/api/v3/order")})
    gateway = make_gateway(server)

    result = control_plane.preview_order(
        db,
        user.id,
        mandate_id=world["mandate"].id,
        symbol="BTCUSDT",
        side="buy",
        quantity="0.5",
        gateway=gateway,
    )
    order = control_plane.confirm_order(
        db,
        user.id,
        order_intent_id=result["intent"].id,
        confirmation=result["confirmation"],
        gateway=gateway,
    )
    assert order.status == "unknown"
    assert order.error_code == "SUBMIT_UNKNOWN"
    # The gateway was contacted exactly once; UNKNOWN is queried, never resubmitted.
    assert server.calls[("POST", "/api/v3/order")] == 1


def test_business_rejection_returns_rejected(db, user_factory, monkeypatch):
    user = user_factory("reject@test.com")
    world = _make_live_world(db, user, monkeypatch)
    server = BinanceMockServer(
        error_paths={
            ("POST", "/api/v3/order"): (400, {"code": -2010, "msg": "Account has insufficient balance"})
        }
    )
    gateway = make_gateway(server)
    result = control_plane.preview_order(
        db,
        user.id,
        mandate_id=world["mandate"].id,
        symbol="BTCUSDT",
        side="buy",
        quantity="0.5",
        gateway=gateway,
    )
    order = control_plane.confirm_order(
        db,
        user.id,
        order_intent_id=result["intent"].id,
        confirmation=result["confirmation"],
        gateway=gateway,
    )
    assert order.status == "rejected"


# ---------------------------------------------------------------------------
# API-key permission hard-check
# ---------------------------------------------------------------------------


def test_unsafe_api_permissions_hard_reject_connection(db, user_factory, monkeypatch):
    user = user_factory("unsafe@test.com")
    world = _make_live_world(db, user, monkeypatch)
    server = BinanceMockServer(
        restrictions={
            "enableWithdrawals": True,  # unsafe: withdrawals enabled on the key
            "enableInternalTransfer": False,
            "permitsUniversalTransfer": False,
            "enableVanillaOptions": False,
            "enableFutures": False,
            "enableMargin": False,
            "enableSpotAndMarginTrading": True,
        }
    )
    gateway = make_gateway(server)

    health = gateway.health(connection_id=world["connection"].id)
    assert health["permissions"]["safe"] is False

    with pytest.raises(control_plane.ControlPlaneError, match="unsafe"):
        control_plane.test_connection(db, user.id, world["connection"].id, gateway=gateway)
    db.refresh(world["connection"])
    assert world["connection"].status == "ERROR"
    assert world["connection"].error_code == "UNSAFE_API_PERMISSIONS"

    # A fresh gateway instance (cold permission cache) must still refuse to submit.
    fresh = make_gateway(server)
    with pytest.raises(GatewayUnavailable, match="UNSAFE_API_PERMISSIONS"):
        fresh.submit_order(
            {
                "connection_id": world["connection"].id,
                "client_order_id": "pg-unsafe",
                "account_id": world["account"].id,
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "MARKET",
                "quantity": "0.5",
            }
        )
    # No order ever reached the venue.
    assert server.calls.get(("POST", "/api/v3/order"), 0) == 0


def _patch_provider(monkeypatch, provider: str = "binance_spot"):
    """The Settings dataclass is frozen: replace the whole instance and patch
    the reference the control plane imported."""
    import dataclasses

    from apps.api.config import get_settings

    patched = dataclasses.replace(get_settings(), live_trading_provider=provider)
    monkeypatch.setattr(
        "packages.live_trading.control_plane.get_settings", lambda: patched
    )


def test_bind_connection_rejects_unsafe_key(db, user_factory, monkeypatch):
    user = user_factory("bind-unsafe@test.com")
    _make_live_world(db, user, monkeypatch)
    _patch_provider(monkeypatch)
    server = BinanceMockServer(
        restrictions={**BinanceMockServer().restrictions, "enableFutures": True}
    )
    gateway = make_gateway(server)
    with pytest.raises(control_plane.ControlPlaneError, match="Connection rejected"):
        control_plane.bind_connection(
            db,
            user.id,
            provider="binance_spot",
            account_label="unsafe-key",
            credentials=CREDENTIALS,
            gateway=gateway,
        )
    row = (
        db.query(BrokerConnection)
        .filter_by(user_id=user.id, account_label="unsafe-key")
        .one()
    )
    assert row.status == "ERROR"
    assert row.error_code == "UNSAFE_API_PERMISSIONS"
    assert "test-api-secret-value" not in row.encrypted_credentials_ref


# ---------------------------------------------------------------------------
# Signing + mapping
# ---------------------------------------------------------------------------


def test_submit_signs_and_maps_ack(db, user_factory, monkeypatch):
    server = BinanceMockServer(order_status="NEW")
    gateway = make_gateway(server)
    ack = gateway.submit_order(
        {
            "connection_id": "conn-1",
            "client_order_id": "pg-12345",
            "account_id": "acct-1",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "MARKET",
            "quantity": "0.5",
        }
    )
    assert ack["state"] == "accepted"
    assert ack["exchange_order_id"] == "123456"
    signature = server.last_order_params["signature"]
    assert len(signature) == 64  # HMAC-SHA256 hex
    assert server.last_order_params["newClientOrderId"] == "pg-12345"
    assert server.last_order_params["quantity"] == "0.5"


def test_query_order_maps_fills(db, user_factory, monkeypatch):
    now_ms = int(time.time() * 1000)
    server = BinanceMockServer(
        query_status="FILLED",
        query_filled=True,
        trades=[
            {
                "id": 77,
                "orderId": 123456,
                "symbol": "BTCUSDT",
                "price": "100",
                "qty": "0.5",
                "commission": "0.1",
                "commissionAsset": "BNB",
                "time": now_ms,
                "isBuyer": True,
            }
        ],
    )
    gateway = make_gateway(server)
    result = gateway.query_order(
        "pg-12345", "acct-1", connection_id="conn-1", symbol="BTCUSDT"
    )
    assert result["state"] == "filled"
    fills = result["order"]["fills"]
    assert fills[0]["broker_fill_id"] == "77"
    assert fills[0]["quantity"] == "0.5"
    assert fills[0]["price"] == "100"
    assert fills[0]["fee"] == "0.1"
    assert fills[0]["fee_currency"] == "BNB"


def test_balances_and_positions_mapping(db, user_factory, monkeypatch):
    server = BinanceMockServer(balance_free="1000", ticker={"BTCUSDT": "100"})
    gateway = make_gateway(server)
    balances = gateway.account_balances("acct-1", connection_id="conn-1")
    assert balances["available"] == "1000"
    assert balances["cash"] == "1000"
    assert balances["equity"] == "1000"
    positions = gateway.positions("acct-1", connection_id="conn-1")
    btc = next(p for p in positions if p["instrument"] == "BTCUSDT")
    assert btc["quantity"] == "0.5"
    assert btc["mark_price"] == "100"
    assert btc["notional"] == "50"


# ---------------------------------------------------------------------------
# End-to-end approved-user small order (mock Binance transport)
# ---------------------------------------------------------------------------


def test_e2e_approved_user_small_order_full_path(db, user_factory, monkeypatch):
    user = user_factory("e2e@test.com")
    world = _make_live_world(db, user, monkeypatch)
    now_ms = int(time.time() * 1000)
    server = BinanceMockServer(
        order_status="NEW",
        query_status="FILLED",
        query_filled=True,
        trades=[
            {
                "id": 1,
                "orderId": 123456,
                "symbol": "BTCUSDT",
                "price": "100",
                "qty": "0.5",
                "commission": "0.1",
                "commissionAsset": "BNB",
                "time": now_ms,
                "isBuyer": True,
            }
        ],
    )
    gateway = make_gateway(server)

    # preview -> confirm (submit ack NEW -> accepted)
    result = control_plane.preview_order(
        db,
        user.id,
        mandate_id=world["mandate"].id,
        symbol="BTCUSDT",
        side="buy",
        quantity="0.5",
        gateway=gateway,
    )
    assert result["trace_id"]
    order = control_plane.confirm_order(
        db,
        user.id,
        order_intent_id=result["intent"].id,
        confirmation=result["confirmation"],
        gateway=gateway,
    )
    assert order.status == "accepted"
    assert order.trace_id == result["trace_id"]

    # background status sync: query -> FILLED + fills
    synced = control_plane.sync_order_status(db, order, gateway=gateway)
    assert synced.status == "filled"
    assert synced.broker_order_id == "123456"
    assert synced.filled_quantity == Decimal("0.5")

    fills = db.query(Fill).filter_by(order_id=order.id).all()
    assert len(fills) == 1
    entries = db.query(LedgerEntry).filter_by(ref_id=fills[0].id).all()
    assert {entry.entry_type for entry in entries} >= {"trade_buy", "fee"}

    # NAV recalculated server-side from gateway cash + position value.
    snapshot = nav.calculate_nav(
        db,
        user_id=user.id,
        account_id=world["account"].id,
        mandate_id=world["mandate"].id,
        gateway=gateway,
    )
    db.commit()
    assert snapshot.nav == Decimal("1050")  # 1000 cash + 0.5 * 100

    # No plaintext secret anywhere in the persisted order state or DB.
    assert "test-api-secret-value" not in json.dumps(order.raw_ack_json)
    stored = db.query(BrokerConnection).filter_by(id=world["connection"].id).one()
    assert "test-api-secret-value" not in stored.encrypted_credentials_ref


def test_cancel_order_reaches_gateway(db, user_factory, monkeypatch):
    user = user_factory("cancel@test.com")
    world = _make_live_world(db, user, monkeypatch)
    server = BinanceMockServer(order_status="NEW")
    gateway = make_gateway(server)
    result = control_plane.preview_order(
        db,
        user.id,
        mandate_id=world["mandate"].id,
        symbol="BTCUSDT",
        side="buy",
        quantity="0.5",
        gateway=gateway,
    )
    order = control_plane.confirm_order(
        db,
        user.id,
        order_intent_id=result["intent"].id,
        confirmation=result["confirmation"],
        gateway=gateway,
    )
    canceled = control_plane.cancel_order(db, user.id, order.client_order_id, gateway=gateway)
    assert canceled.status == "canceled"
    assert server.calls[("DELETE", "/api/v3/order")] == 1


# ---------------------------------------------------------------------------
# Reconciliation against the real gateway
# ---------------------------------------------------------------------------


def test_reconciliation_ok_when_ledger_matches_exchange(db, user_factory, monkeypatch):
    user = user_factory("recon-ok@test.com")
    world = _make_live_world(db, user, monkeypatch)
    # Ledger cash mirrors the exchange balance (1000).
    ledger.post_entry(
        db,
        user_id=user.id,
        account_id=world["account"].id,
        entry_type="cash_deposit",
        amount=Decimal("1000"),
        idempotency_key="deposit:e2e",
        trace_id="trace-deposit",
    )
    db.commit()
    server = BinanceMockServer(balance_free="1000")
    gateway = make_gateway(server)
    row = reconciliation_service.reconcile_account(
        db,
        user_id=user.id,
        account_id=world["account"].id,
        mandate=world["mandate"],
        connection=world["connection"],
        gateway=gateway,
        trace_id="trace-recon-ok",
    )
    db.commit()
    assert row.status == "ok"
    assert row.differences_json == []
    db.refresh(world["mandate"])
    assert world["mandate"].paused is False


class _RaisingGateway:
    name = "raising"

    def account_balances(self, account_id, *, connection_id=None):
        raise GatewayUnavailable("venue down")


def test_reconciliation_gateway_error_pauses_mandate(db, user_factory, monkeypatch):
    user = user_factory("recon-error@test.com")
    world = _make_live_world(db, user, monkeypatch)
    row = reconciliation_service.reconcile_account(
        db,
        user_id=user.id,
        account_id=world["account"].id,
        mandate=world["mandate"],
        connection=world["connection"],
        gateway=_RaisingGateway(),
        trace_id="trace-recon-error",
    )
    db.commit()
    assert row.status == "error"
    db.refresh(world["mandate"])
    assert world["mandate"].paused is True


# ---------------------------------------------------------------------------
# Honest mock semantics
# ---------------------------------------------------------------------------


def test_mock_gateway_reports_disabled_not_error(db, user_factory, monkeypatch):
    user = user_factory("mock-honesty@test.com")
    world = _make_live_world(db, user, monkeypatch)
    result = control_plane.test_connection(
        db, user.id, world["connection"].id, gateway=MockExecutionGateway()
    )
    assert result["status"] == "DISCONNECTED"
    assert result["health"]["status"] == "DISABLED"
    db.refresh(world["connection"])
    assert world["connection"].status == "DISCONNECTED"
    assert world["connection"].error_code == "GATEWAY_DISABLED"


def test_bind_and_revoke_connection(db, user_factory, monkeypatch):
    user = user_factory("bind@test.com")
    world = _make_live_world(db, user, monkeypatch)
    _patch_provider(monkeypatch)
    server = BinanceMockServer()
    gateway = make_gateway(server)

    connection = control_plane.bind_connection(
        db,
        user.id,
        provider="binance_spot",
        account_label="my-binance",
        credentials=CREDENTIALS,
        gateway=gateway,
    )
    assert connection.status == "HEALTHY"
    assert "test-api-secret-value" not in connection.encrypted_credentials_ref
    listed = control_plane.list_connections(db, user.id)
    assert any(item["account_label"] == "my-binance" and item["has_credentials"] for item in listed)
    assert all("api_secret" not in json.dumps(item) for item in listed)

    revoked = control_plane.revoke_connection(db, user.id, world["connection"].id)
    assert revoked.status == "REVOKED"
    assert revoked.revoked_at is not None

    # The live mandate bound to the revoked connection must be paused.
    db.refresh(world["mandate"])
    assert world["mandate"].paused is True
    assert world["mandate"].pause_reason == "connection_revoked"
