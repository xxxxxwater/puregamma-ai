"""Binance Spot LIVE execution gateway for the Trading Control Plane.

This is the FIRST real-exchange gateway. It implements the
``ExecutionGateway`` protocol directly against the Binance Spot REST API
(``https://api.binance.com`` by default; ``LIVE_TRADING_BINANCE_BASE_URL`` can
point at a sandbox for rehearsal) and follows the exact semantics of the
Nautilus runtime's ``BinanceSpotTestnetAdapter`` so both layers behave alike:

- credentials are resolved per broker connection through the Fernet/KMS
  secret store — plaintext never touches the database, logs, or order acks;
- a submit timeout / transport failure / 5xx raises ``GatewayOrderUnknown``:
  the control plane records the order as UNKNOWN and only ever QUERIES;
- Binance business rejections (4xx codes) map to a REJECTED ack — Binance
  definitively refused the order, so no retry ambiguity exists;
- the API key permission set is hard-verified (``/sapi/v1/account/
  apiRestrictions``): withdrawal / internal-transfer / universal-transfer /
  options / futures / margin enabled on the key => the connection is refused
  and the health check reports ``permissions.safe=False``;
- withdrawals and transfers have no method path at all (defense in depth).

Only the Trading Control Plane may construct or call this gateway. It is
selected by ``LIVE_TRADING_GATEWAY=binance`` + ``LIVE_TRADING_ENABLED=true`` +
``LIVE_TRADING_PROVIDER=binance_spot`` in ``gateway_adapter.py``.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from apps.api.config import get_settings
from packages.live_trading.gateway_adapter import GatewayOrderUnknown, GatewayUnavailable

# Binance spot order status -> internal LiveOrderStatus values used by the
# control plane. Mirrors services/nautilus-runtime/adapters/binance_spot_testnet.py.
ORDER_STATE_MAP = {
    "NEW": "accepted",
    "PARTIALLY_FILLED": "partially_filled",
    "FILLED": "filled",
    "CANCELED": "canceled",
    "EXPIRED": "expired",
    "REJECTED": "rejected",
}

# Quote assets used to derive cash/equity for spot accounts.
QUOTE_ASSETS = ("USDT", "USDC", "BUSD", "FDUSD")

# Client-side (4xx) Binance error codes map to a structured REJECTED ack;
# transport failures, timeouts and 5xx responses raise and become UNKNOWN
# upstream. Timestamp skew (-1021) is re-synced and retried exactly once.
REJECT_ERROR_PREFIX = {-1000, -1100, -1101, -1102, -1103, -1104, -1105, -1121, -1125}

# API-key restrictions that must ALL be disabled for a spot-only trading key.
FORBIDDEN_KEY_PERMISSIONS = (
    "enableWithdrawals",
    "enableInternalTransfer",
    "permitsUniversalTransfer",
    "enableVanillaOptions",
    "enableFutures",
    "enableMargin",
)

_PERMISSION_CACHE_TTL_SECONDS = 60.0


class BinanceAPIError(RuntimeError):
    def __init__(self, code: int, message: str):
        super().__init__(f"binance error {code}: {message[:200]}")
        self.code = code
        self.message = message

    @property
    def is_reject(self) -> bool:
        # Binance business rejections (filters, balance, permissions, rate
        # limits) carry -1xxx/-2xxx codes; timestamp sync (-1021) is retried
        # upstream and transport/5xx failures raise instead.
        return -4000 < self.code <= -1000 and self.code != -1021

    def to_reject(self) -> dict:
        return {
            "state": "rejected",
            "error": f"BINANCE_{abs(self.code)}",
            "error_detail": self.message[:240],
        }


class BinanceSpotLiveGateway:
    """Real Binance Spot gateway for LIVE (production) execution."""

    name = "binance_spot"
    venue = "BINANCE"
    environment = "production"

    def __init__(
        self,
        *,
        session_factory: Callable[[], Any] | None = None,
        credential_resolver: Callable[[str], dict[str, Any]] | None = None,
        base_url: str | None = None,
        recv_window_ms: int | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        settings = get_settings()
        self._session_factory = session_factory
        self._credential_resolver = credential_resolver
        self.base_url = (
            base_url or settings.live_trading_binance_base_url
        ).rstrip("/")
        self.recv_window_ms = recv_window_ms or settings.live_trading_binance_recv_window_ms
        self.timeout = timeout or settings.live_trading_order_timeout_seconds
        self._transport = transport
        self._time_offset_ms = 0
        self._permission_cache: dict[str, tuple[float, dict]] = {}

    # ------------------------------------------------------------- credentials

    def _default_resolver(self, connection_id: str) -> dict[str, Any]:
        """DB-backed resolver: BrokerConnection -> Fernet-decrypted secrets."""
        from packages.database.models import BrokerConnection
        from packages.database.session import SessionLocal
        from packages.live_trading.secret_store import decrypt_secrets

        db = SessionLocal()
        try:
            connection = (
                db.query(BrokerConnection).filter_by(id=connection_id).one_or_none()
            )
            if connection is None:
                raise GatewayUnavailable("Broker connection not found")
            if connection.revoked_at is not None:
                raise GatewayUnavailable("Broker connection is revoked")
            if connection.environment != "production":
                raise GatewayUnavailable(
                    f"Connection environment '{connection.environment}' is not routable "
                    "through the LIVE gateway"
                )
            secrets_dict = decrypt_secrets(connection.encrypted_credentials_ref)
            if not secrets_dict.get("api_key") or not secrets_dict.get("api_secret"):
                raise GatewayUnavailable("Stored broker credentials are incomplete")
            return secrets_dict
        finally:
            db.close()

    def _credentials(self, connection_id: str | None) -> dict[str, Any]:
        if not connection_id:
            raise GatewayUnavailable("No broker connection bound to this order")
        resolver = self._credential_resolver or self._default_resolver
        return resolver(connection_id)

    # -------------------------------------------------------------------- HTTP

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, transport=self._transport)

    def _timestamp_ms(self) -> int:
        return int(time.time() * 1000) + self._time_offset_ms

    @staticmethod
    def _sign(api_secret: str, params: dict) -> dict:
        query = urlencode(params, doseq=True)
        signature = hmac.new(
            api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        return {**params, "signature": signature}

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        *,
        credentials: dict[str, Any] | None = None,
        signed: bool = False,
    ):
        params = dict(params or {})
        headers: dict[str, str] = {}
        api_key = ""
        api_secret = ""
        if signed:
            credentials = credentials or {}
            api_key = str(credentials.get("api_key") or "")
            api_secret = str(credentials.get("api_secret") or "")
            if not api_key or not api_secret:
                raise BinanceAPIError(-9000, "Binance credentials are not configured")
            headers["X-MBX-APIKEY"] = api_key
            params.setdefault("recvWindow", self.recv_window_ms)
            params["timestamp"] = self._timestamp_ms()
            params = self._sign(api_secret, params)
        try:
            with self._client() as client:
                response = client.request(
                    method, f"{self.base_url}{path}", params=params, headers=headers
                )
        except httpx.TimeoutException as exc:
            raise GatewayOrderUnknown(
                f"Binance request timed out after {self.timeout}s: {str(exc)[:200]}"
            ) from exc
        except httpx.NetworkError as exc:
            raise GatewayOrderUnknown(
                f"Binance transport failure: {str(exc)[:200]}"
            ) from exc
        if response.status_code >= 400:
            payload: dict = {}
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            code = int(payload.get("code", response.status_code))
            error = BinanceAPIError(code, payload.get("msg", f"HTTP {response.status_code}"))
            if error.code == -1021 and signed:
                # Clock skew: sync against server time and retry exactly once.
                self.sync_time(credentials)
                params["timestamp"] = self._timestamp_ms()
                params = self._sign(api_secret, {k: v for k, v in params.items() if k != "signature"})
                with self._client() as client:
                    response = client.request(
                        method, f"{self.base_url}{path}", params=params, headers=headers
                    )
                if response.status_code >= 400:
                    try:
                        payload = response.json()
                    except ValueError:
                        payload = {}
                    raise BinanceAPIError(
                        int(payload.get("code", response.status_code)),
                        payload.get("msg", f"HTTP {response.status_code}"),
                    )
                return response.json()
            raise error
        if response.status_code == 200 and not response.content:
            return {}
        return response.json()

    def sync_time(self, credentials: dict[str, Any] | None = None) -> int:
        server = self._request("GET", "/api/v3/time", credentials=credentials)
        self._time_offset_ms = int(server["serverTime"]) - int(time.time() * 1000)
        return self._time_offset_ms

    # ------------------------------------------------------ key permission gate

    def _check_permissions(self, credentials: dict[str, Any]) -> dict:
        """Hard-verify the API key permission set. Any forbidden capability
        enabled on the key => ``safe=False`` and the connection is refused."""
        payload = self._request(
            "GET", "/sapi/v1/account/apiRestrictions", signed=True, credentials=credentials
        )
        checks: dict[str, Any] = {}
        unsafe: list[str] = []
        for field in FORBIDDEN_KEY_PERMISSIONS:
            value = bool(payload.get(field, False))
            checks[field] = value
            if value:
                unsafe.append(field)
        spot_trading = bool(payload.get("enableSpotAndMarginTrading", True))
        checks["enableSpotAndMarginTrading"] = spot_trading
        if not spot_trading:
            unsafe.append("enableSpotAndMarginTrading=false")
        return {"safe": not unsafe, "unsafe_permissions": unsafe, "checks": checks}

    def _verify_permissions(
        self, connection_id: str, credentials: dict[str, Any], *, force: bool = False
    ) -> dict:
        cached = self._permission_cache.get(connection_id)
        if cached and not force and (time.monotonic() - cached[0]) < _PERMISSION_CACHE_TTL_SECONDS:
            permissions = cached[1]
        else:
            permissions = self._check_permissions(credentials)
            self._permission_cache[connection_id] = (time.monotonic(), permissions)
        if not permissions.get("safe"):
            raise GatewayUnavailable(
                "UNSAFE_API_PERMISSIONS: " + ", ".join(permissions.get("unsafe_permissions") or ["unknown"])
            )
        return permissions

    # ------------------------------------------------------------- interface

    def health(self, connection_id: str | None = None) -> dict[str, Any]:
        """Health check for one connection: ping + key permission hard-check
        + spot trading capability. Never echoes credentials."""
        credentials = self._credentials(connection_id)
        try:
            self._request("GET", "/api/v3/ping")
        except GatewayOrderUnknown as exc:
            raise GatewayUnavailable(str(exc)) from exc
        try:
            permissions = self._check_permissions(credentials)
        except BinanceAPIError as exc:
            raise GatewayUnavailable(f"Binance permission check failed: {exc}") from exc
        status = "HEALTHY"
        try:
            account = self._request("GET", "/api/v3/account", signed=True, credentials=credentials)
            if not bool(account.get("canTrade", True)):
                status = "DEGRADED"
        except (BinanceAPIError, GatewayOrderUnknown):
            status = "DEGRADED"
        return {
            "status": status,
            "adapter": self.name,
            "venue": self.venue,
            "environment": self.environment,
            "live": True,
            "withdrawal": False,
            "transfer": False,
            "permissions": permissions,
        }

    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        connection_id = payload.get("connection_id")
        credentials = self._credentials(connection_id)
        self._verify_permissions(connection_id, credentials)

        client_order_id = str(payload["client_order_id"])
        symbol = str(payload.get("symbol") or payload.get("instrument") or "").upper()
        if not symbol:
            raise GatewayUnavailable("Symbol is required to submit a Binance order")
        params: dict = {
            "symbol": symbol,
            "side": str(payload.get("side") or "BUY").upper(),
            "type": str(payload.get("order_type") or "MARKET").upper(),
            "quantity": _format_quantity(payload.get("quantity")),
            "newClientOrderId": client_order_id,
            "newOrderRespType": "FULL",
        }
        if params["type"] == "LIMIT":
            if payload.get("limit_price") is None:
                raise GatewayUnavailable("limit_price is required for LIMIT orders")
            params["timeInForce"] = "GTC"
            params["price"] = _format_quantity(payload.get("limit_price"))
        try:
            result = self._request(
                "POST", "/api/v3/order", params, signed=True, credentials=credentials
            )
        except BinanceAPIError as exc:
            if exc.is_reject:
                return {
                    **exc.to_reject(),
                    "client_order_id": client_order_id,
                    "instrument": symbol,
                    "exchange_order_id": None,
                }
            raise GatewayOrderUnknown(
                f"Binance submit indeterminate (HTTP {abs(exc.code)}); order state unknown"
            ) from exc
        except GatewayOrderUnknown:
            raise
        mapped = self._map_order(result, payload.get("account_id"))
        mapped["client_order_id"] = client_order_id
        return mapped

    def query_order(
        self,
        client_order_id: str,
        account_id: str,
        *,
        connection_id: str | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        credentials = self._credentials(connection_id)
        if not symbol:
            raise GatewayOrderUnknown(
                "Symbol is required to query a Binance order by client order id"
            )
        try:
            payload = self._request(
                "GET",
                "/api/v3/order",
                {"symbol": symbol.upper(), "origClientOrderId": client_order_id},
                signed=True,
                credentials=credentials,
            )
        except BinanceAPIError as exc:
            if exc.code == -2013:  # order does not exist on the venue
                return {
                    "state": "canceled",
                    "reason": "not_found_on_venue",
                    "order": None,
                }
            raise GatewayOrderUnknown(
                f"Binance order query failed: {str(exc)[:200]}"
            ) from exc
        mapped = self._map_order(payload, account_id)
        fills = self._order_fills(symbol, mapped.get("exchange_order_id"), credentials)
        return {"state": mapped["state"], "order": {**mapped, "fills": fills}}

    def cancel_order(
        self,
        client_order_id: str,
        account_id: str,
        *,
        connection_id: str | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        credentials = self._credentials(connection_id)
        if not symbol:
            raise GatewayUnavailable("Symbol is required to cancel a Binance order")
        try:
            payload = self._request(
                "DELETE",
                "/api/v3/order",
                {"symbol": symbol.upper(), "origClientOrderId": client_order_id},
                signed=True,
                credentials=credentials,
            )
        except BinanceAPIError as exc:
            if exc.code == -2011:  # unknown order -> already gone
                return {"client_order_id": client_order_id, "state": "canceled"}
            raise GatewayUnavailable(f"Binance cancel failed: {str(exc)[:200]}") from exc
        mapped = self._map_order(payload, account_id)
        return {"client_order_id": client_order_id, "state": mapped["state"]}

    def account_balances(
        self, account_id: str, *, connection_id: str | None = None
    ) -> dict[str, Any]:
        credentials = self._credentials(connection_id)
        try:
            payload = self._request("GET", "/api/v3/account", signed=True, credentials=credentials)
        except BinanceAPIError as exc:
            raise GatewayUnavailable(f"Binance balances unavailable: {exc}") from exc
        quote = _quote_balance(payload)
        return {
            "cash": str(quote["total"]),
            "available": str(quote["free"]),
            "equity": str(quote["total"]),
        }

    def positions(
        self, account_id: str, *, connection_id: str | None = None
    ) -> list[dict[str, Any]]:
        credentials = self._credentials(connection_id)
        try:
            payload = self._request("GET", "/api/v3/account", signed=True, credentials=credentials)
        except BinanceAPIError as exc:
            raise GatewayUnavailable(f"Binance positions unavailable: {exc}") from exc
        symbols: list[str] = []
        quantities: dict[str, Decimal] = {}
        for entry in payload.get("balances", []):
            asset = str(entry.get("asset", ""))
            if asset in QUOTE_ASSETS:
                continue
            quantity = Decimal(str(entry.get("free", 0) or 0)) + Decimal(
                str(entry.get("locked", 0) or 0)
            )
            if quantity <= 0:
                continue
            symbols.append(f"{asset}USDT")
            quantities[f"{asset}USDT"] = quantity
        prices = self._ticker_prices(symbols)
        positions: list[dict[str, Any]] = []
        for symbol in symbols:
            mark = prices.get(symbol)
            quantity = quantities[symbol]
            positions.append(
                {
                    "account_id": account_id,
                    "instrument": symbol,
                    "quantity": str(quantity),
                    "side": "LONG",
                    "average_price": "0",
                    "mark_price": str(mark) if mark is not None else None,
                    "notional": _format_quantity(quantity * mark) if mark is not None else None,
                    "unrealized_pnl": "0",
                    "realized_pnl": "0",
                    "leverage": 1,
                    "mode": "LIVE",
                }
            )
        return positions

    def fetch_prices(
        self, symbols: list[str], *, connection_id: str | None = None
    ) -> dict[str, Decimal]:
        """Batch ticker prices (used by the server price feed for NAV marking)."""
        credentials = self._credentials(connection_id)
        return self._ticker_prices([s.upper() for s in symbols], credentials)

    # ------------------------------------------------------------- internals

    def _map_order(self, payload: dict, account_id: str | None = None) -> dict:
        executed = Decimal(str(payload.get("executedQty", 0) or 0))
        quote_qty = Decimal(str(payload.get("cummulativeQuoteQty", 0) or 0))
        average = Decimal(str(payload.get("price", 0) or 0))
        if executed and quote_qty:
            average = quote_qty / executed
        return {
            "account_id": account_id,
            "client_order_id": payload.get("clientOrderId", ""),
            "exchange_order_id": str(payload.get("orderId", "")),
            "broker_order_id": str(payload.get("orderId", "")),
            "instrument": payload.get("symbol", ""),
            "venue": self.venue,
            "side": str(payload.get("side", "")).lower(),
            "order_type": str(payload.get("type", "")).lower(),
            "quantity": _format_quantity(payload.get("origQty", 0)),
            "state": ORDER_STATE_MAP.get(payload.get("status", ""), "unknown"),
            "filled_quantity": _format_quantity(executed),
            "remaining_quantity": _format_quantity(
                Decimal(str(payload.get("origQty", 0) or 0)) - executed
            ),
            "average_price": _format_quantity(average) if executed else None,
        }

    def _ticker_prices(
        self, symbols: list[str], credentials: dict[str, Any] | None = None
    ) -> dict[str, Decimal]:
        if not symbols:
            return {}
        unique = list(dict.fromkeys(symbols))
        try:
            payload = self._request(
                "GET",
                "/api/v3/ticker/price",
                {"symbols": _json_list(unique)},
                credentials=credentials,
            )
        except (GatewayOrderUnknown, GatewayUnavailable, BinanceAPIError):
            return {}
        prices: dict[str, Decimal] = {}
        for item in payload if isinstance(payload, list) else [payload]:
            try:
                prices[str(item.get("symbol", "")).upper()] = Decimal(
                    str(item.get("price"))
                )
            except Exception:
                continue
        return prices

    def _order_fills(
        self,
        symbol: str,
        exchange_order_id: str | None,
        credentials: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not exchange_order_id:
            return []
        try:
            payload = self._request(
                "GET",
                "/api/v3/myTrades",
                {"symbol": symbol.upper(), "orderId": exchange_order_id},
                signed=True,
                credentials=credentials,
            )
        except (BinanceAPIError, GatewayOrderUnknown):
            return []
        fills = []
        for trade in payload:
            fills.append(
                {
                    "broker_fill_id": str(trade.get("id", "")),
                    "exchange_order_id": str(trade.get("orderId", "")),
                    "quantity": _format_quantity(trade.get("qty", 0)),
                    "price": _format_quantity(trade.get("price", 0)),
                    "fee": _format_quantity(trade.get("commission", 0)),
                    "fee_currency": str(trade.get("commissionAsset") or "USD"),
                    "executed_at": datetime.fromtimestamp(
                        int(trade.get("time", 0)) / 1000, tz=timezone.utc
                    ).isoformat(),
                }
            )
        return fills

    # ------------------------------------------------------ forbidden rails

    def withdraw(self, *args, **kwargs):
        raise RuntimeError("Binance live gateway: withdrawals are hard-disabled")

    def transfer(self, *args, **kwargs):
        raise RuntimeError("Binance live gateway: transfers are hard-disabled")


def _format_quantity(value: Any) -> str:
    """Decimal-safe Binance quantity/price formatting (no binary float)."""
    try:
        return f"{Decimal(str(value)):.8f}".rstrip("0").rstrip(".")
    except Exception:
        return "0"


def _json_list(items: list[str]) -> str:
    import json

    return json.dumps(items)


def _quote_balance(payload: dict) -> dict[str, Decimal]:
    total = Decimal("0")
    free = Decimal("0")
    for entry in payload.get("balances", []):
        if str(entry.get("asset", "")) not in QUOTE_ASSETS:
            continue
        total += Decimal(str(entry.get("free", 0) or 0)) + Decimal(
            str(entry.get("locked", 0) or 0)
        )
        free += Decimal(str(entry.get("free", 0) or 0))
    return {"total": total, "free": free}
