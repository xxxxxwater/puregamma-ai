from __future__ import annotations

import hashlib
import hmac
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Binance spot order status -> internal OrderState (packages.trading OrderState).
ORDER_STATE_MAP = {
    "NEW": "ACCEPTED",
    "PARTIALLY_FILLED": "PARTIALLY_FILLED",
    "FILLED": "FILLED",
    "CANCELED": "CANCELED",
    "EXPIRED": "EXPIRED",
    "REJECTED": "REJECTED",
}

# Client-side (4xx) Binance error codes map to a structured REJECTED ack;
# transport failures and 5xx responses raise and become UNKNOWN upstream.
REJECT_ERROR_PREFIX = {-1000, -1100, -1101, -1102, -1103, -1104, -1105, -1121, -1125}


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
            "state": "REJECTED",
            "error": f"BINANCE_{abs(self.code)}",
            "error_detail": self.message[:240],
        }


class BinanceSpotTestnetAdapter:
    """Binance Spot Testnet (https://testnet.binance.vision) gateway.

    Real HMAC-signed order submission against the Binance spot sandbox.
    Withdrawals and transfers are hard-disabled; this adapter is spot order
    flow only and never holds or moves funds off-venue.
    """

    name = "binance_spot_testnet"
    venue = "BINANCE"
    environment = "testnet"

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str | None = None,
        *,
        recv_window_ms: int = 5000,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.api_key = api_key if api_key is not None else os.getenv("BINANCE_TESTNET_API_KEY", "")
        self._api_secret = (
            api_secret if api_secret is not None else os.getenv("BINANCE_TESTNET_API_SECRET", "")
        )
        self.base_url = (
            base_url or os.getenv("NAUTILUS_BINANCE_TESTNET_BASE_URL") or "https://testnet.binance.vision"
        ).rstrip("/")
        self.recv_window_ms = recv_window_ms
        self.timeout = timeout
        self._transport = transport
        self._time_offset_ms = 0
        self._order_symbols: dict[str, str] = {}

    # ------------------------------------------------------------------ HTTP

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, transport=self._transport)

    def _timestamp_ms(self) -> int:
        return int(time.time() * 1000) + self._time_offset_ms

    def _sign(self, params: dict) -> dict:
        query = urlencode(params, doseq=True)
        signature = hmac.new(
            self._api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        return {**params, "signature": signature}

    def _request(
        self, method: str, path: str, params: dict | None = None, *, signed: bool = False
    ):
        params = dict(params or {})
        headers: dict[str, str] = {}
        if signed:
            if not self.api_key or not self._api_secret:
                raise BinanceAPIError(-9000, "Binance testnet credentials are not configured")
            headers["X-MBX-APIKEY"] = self.api_key
            params.setdefault("recvWindow", self.recv_window_ms)
            params["timestamp"] = self._timestamp_ms()
            params = self._sign(params)
        with self._client() as client:
            response = client.request(method, f"{self.base_url}{path}", params=params, headers=headers)
        if response.status_code >= 400:
            payload: dict = {}
            try:
                payload = response.json()
            except ValueError:
                pass
            code = int(payload.get("code", response.status_code))
            error = BinanceAPIError(code, payload.get("msg", f"HTTP {response.status_code}"))
            if error.code == -1021 and signed:
                # Clock skew: sync against server time and retry exactly once.
                self.sync_time()
                params["timestamp"] = self._timestamp_ms()
                params = self._sign({k: v for k, v in params.items() if k != "signature"})
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

    def sync_time(self) -> int:
        server = self._request("GET", "/api/v3/time")
        self._time_offset_ms = int(server["serverTime"]) - int(time.time() * 1000)
        return self._time_offset_ms

    # ------------------------------------------------------------- interface

    def connect(self) -> dict:
        return self.health_check()

    def disconnect(self) -> dict:
        return {"status": "DISCONNECTED", "adapter": self.name}

    def health_check(self) -> dict:
        try:
            self._request("GET", "/api/v3/ping")
            status = "HEALTHY"
        except Exception:
            status = "DEGRADED"
        return {
            "status": status,
            "adapter": self.name,
            "venue": self.venue,
            "environment": self.environment,
            "live": False,
            "withdrawal": False,
            "transfer": False,
        }

    def fetch_price(self, symbol: str) -> dict:
        payload = self._request("GET", "/api/v3/ticker/price", {"symbol": symbol.upper()})
        return {
            "symbol": payload["symbol"],
            "price": float(payload["price"]),
            "timestamp": utc_iso(),
            "provider": self.name,
        }

    def fetch_order_book(self, symbol: str, limit: int = 20) -> dict:
        payload = self._request(
            "GET", "/api/v3/depth", {"symbol": symbol.upper(), "limit": min(limit, 100)}
        )
        return {
            "symbol": symbol.upper(),
            "bids": [[float(price), float(qty)] for price, qty in payload.get("bids", [])],
            "asks": [[float(price), float(qty)] for price, qty in payload.get("asks", [])],
            "timestamp": utc_iso(),
            "provider": self.name,
        }

    def fetch_account(self, account_id: str) -> dict:
        payload = self._request("GET", "/api/v3/account", signed=True)
        balances = [
            {
                "asset": entry["asset"],
                "free": float(entry["free"]),
                "locked": float(entry["locked"]),
            }
            for entry in payload.get("balances", [])
            if float(entry["free"]) or float(entry["locked"])
        ]
        quote = next((b for b in balances if b["asset"] in {"USDT", "BUSD"}), None)
        equity = (quote["free"] + quote["locked"]) if quote else 0.0
        return {
            "account_id": account_id,
            "venue": self.venue,
            "environment": self.environment,
            "balances": balances,
            "balance": equity,
            "equity": equity,
            "available_margin": quote["free"] if quote else 0.0,
            "daily_pnl": 0.0,
            "drawdown": 0.0,
            "exposure": 0.0,
            "stale": False,
            "can_trade": bool(payload.get("canTrade", True)),
        }

    def fetch_positions(self, account_id: str) -> list[dict]:
        account = self.fetch_account(account_id)
        positions = []
        for balance in account["balances"]:
            if balance["asset"] in {"USDT", "BUSD", "USD"}:
                continue
            quantity = balance["free"] + balance["locked"]
            symbol = f"{balance['asset']}USDT"
            mark = 0.0
            try:
                mark = float(self.fetch_price(symbol)["price"])
            except Exception:
                pass
            positions.append(
                {
                    "account_id": account_id,
                    "instrument": symbol,
                    "quantity": quantity,
                    "side": "LONG",
                    "average_price": 0.0,
                    "mark_price": mark,
                    "unrealized_pnl": 0.0,
                    "realized_pnl": 0.0,
                    "leverage": 1,
                    "mode": "TESTNET",
                    "updated_at": utc_iso(),
                }
            )
        return positions

    def _map_order(self, payload: dict, account_id: str | None = None) -> dict:
        executed = float(payload.get("executedQty", 0) or 0)
        quote_qty = float(payload.get("cummulativeQuoteQty", 0) or 0)
        average = float(payload["price"]) if float(payload.get("price", 0) or 0) else None
        if executed and quote_qty:
            average = quote_qty / executed
        client_order_id = payload.get("clientOrderId", "")
        if client_order_id and payload.get("symbol"):
            self._order_symbols[client_order_id] = payload["symbol"]
        return {
            "account_id": account_id,
            "client_order_id": client_order_id,
            "exchange_order_id": str(payload.get("orderId", "")),
            "instrument": payload.get("symbol", ""),
            "venue": self.venue,
            "side": payload.get("side", ""),
            "order_type": payload.get("type", ""),
            "quantity": float(payload.get("origQty", 0) or 0),
            "state": ORDER_STATE_MAP.get(payload.get("status", ""), "UNKNOWN"),
            "filled_quantity": executed,
            "remaining_quantity": max(
                0.0, float(payload.get("origQty", 0) or 0) - executed
            ),
            "average_price": average,
            "updated_at": utc_iso(),
        }

    def submit_order(self, order: dict) -> dict:
        client_order_id = order["client_order_id"]
        symbol = str(order["instrument"]).upper()
        params: dict = {
            "symbol": symbol,
            "side": str(order["side"]).upper(),
            "type": str(order.get("order_type", "MARKET")).upper(),
            "quantity": f"{float(order['quantity']):.8f}".rstrip("0").rstrip("."),
            "newClientOrderId": client_order_id,
            "newOrderRespType": "FULL",
        }
        if params["type"] == "LIMIT":
            params["timeInForce"] = "GTC"
            params["price"] = f"{float(order['price']):.8f}".rstrip("0").rstrip(".")
        self._order_symbols[client_order_id] = symbol
        try:
            payload = self._request("POST", "/api/v3/order", params, signed=True)
        except BinanceAPIError as exc:
            if exc.is_reject:
                return {
                    **exc.to_reject(),
                    "client_order_id": client_order_id,
                    "instrument": symbol,
                    "exchange_order_id": None,
                }
            raise
        mapped = self._map_order(payload, order.get("account_id"))
        mapped["client_order_id"] = client_order_id
        return mapped

    def fetch_order(self, client_order_id: str) -> dict | None:
        symbol = self._order_symbols.get(client_order_id)
        if not symbol:
            return None
        try:
            payload = self._request(
                "GET",
                "/api/v3/order",
                {"symbol": symbol, "origClientOrderId": client_order_id},
                signed=True,
            )
        except BinanceAPIError as exc:
            if exc.code == -2013:  # Order does not exist
                return None
            raise
        return self._map_order(payload)

    def fetch_open_orders(self, account_id: str) -> list[dict]:
        orders: list[dict] = []
        symbols = list(dict.fromkeys(self._order_symbols.values()))
        if not symbols:
            payload = self._request("GET", "/api/v3/openOrders", signed=True)
            return [self._map_order(item, account_id) for item in payload]
        for symbol in symbols:
            payload = self._request(
                "GET", "/api/v3/openOrders", {"symbol": symbol}, signed=True
            )
            orders.extend(self._map_order(item, account_id) for item in payload)
        return orders

    def cancel_order(self, account_id: str, client_order_id: str) -> dict:
        symbol = self._order_symbols.get(client_order_id)
        if not symbol:
            return {"client_order_id": client_order_id, "state": "UNKNOWN"}
        payload = self._request(
            "DELETE",
            "/api/v3/order",
            {"symbol": symbol, "origClientOrderId": client_order_id},
            signed=True,
        )
        return self._map_order(payload, account_id)

    def fetch_fills(self, account_id: str, since: int | None = None) -> list[dict]:
        fills: list[dict] = []
        for symbol in dict.fromkeys(self._order_symbols.values()):
            params: dict = {"symbol": symbol}
            if since is not None:
                params["startTime"] = int(since)
            payload = self._request("GET", "/api/v3/myTrades", params, signed=True)
            for trade in payload:
                fills.append(
                    {
                        "account_id": account_id,
                        "exchange_order_id": str(trade.get("orderId", "")),
                        "instrument": symbol,
                        "side": "BUY" if trade.get("isBuyer") else "SELL",
                        "quantity": float(trade["qty"]),
                        "price": float(trade["price"]),
                        "commission": float(trade.get("commission", 0)),
                        "commission_asset": trade.get("commissionAsset"),
                        "trade_id": str(trade.get("id", "")),
                        "timestamp": datetime.fromtimestamp(
                            int(trade["time"]) / 1000, tz=timezone.utc
                        ).isoformat(),
                    }
                )
        return fills

    def reconcile(self, account_id: str) -> dict:
        return {
            "account": self.fetch_account(account_id),
            "positions": self.fetch_positions(account_id),
            "open_orders": self.fetch_open_orders(account_id),
            "fills": self.fetch_fills(account_id),
        }

    # ------------------------------------------------------ forbidden rails

    def withdraw(self, *args, **kwargs):
        raise RuntimeError("Binance testnet adapter: withdrawals are disabled")

    def transfer(self, *args, **kwargs):
        raise RuntimeError("Binance testnet adapter: transfers are disabled")
