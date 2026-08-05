"""Binance read-only private account adapter.

Signed endpoint used: ``GET /api/v3/account`` (HMAC-SHA256 query signature,
``X-MBX-APIKEY`` header). This endpoint already reports ``canTrade`` /
``canWithdraw`` / ``canDeposit`` for the key, which we surface as verified
permission flags.

Finer-grained key restrictions live behind ``GET /sapi/v1/account/apiRestrictions``,
which requires the separate ``sapi`` auth scope and possibly extra key
permissions. We deliberately do NOT call it: the read-only intent is
satisfied by ``/api/v3/account`` and we record what the venue exposes there.

Prices come from the unsigned public ``GET /api/v3/ticker/price`` spot
endpoint (USD stablecoins are priced at 1.0), mirroring how the existing
Hyperliquid sync uses venue-native public mids.

Testnet: ``https://testnet.binance.vision`` when ``environment="testnet"``.

No order, trade, or withdrawal endpoint is ever called.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any
from urllib.parse import urlencode

import requests

from packages.data.cex_private.base import (
    USD_STABLECOINS,
    CexAdapterError,
    CexPermissionDenied,
    CexPrivateAdapter,
    NormalizedHolding,
    PermissionCheck,
)


class BinancePrivateAdapter(CexPrivateAdapter):
    venue = "binance"
    production_base_url = "https://api.binance.com"
    testnet_base_url = "https://testnet.binance.vision"

    def _decode(self, response: requests.Response) -> Any:
        try:
            payload = response.json()
        except ValueError as exc:
            raise CexAdapterError(f"binance returned non-JSON response (HTTP {response.status_code})") from exc
        if response.status_code in {401, 403}:
            raise CexPermissionDenied("binance rejected the API key/secret (check read-only permissions and IP restrictions)")
        if response.status_code >= 400:
            code = payload.get("code") if isinstance(payload, dict) else None
            if code in {-2014, -2015, -2016, -1100, -1102}:
                raise CexPermissionDenied("binance rejected the API key/secret (check read-only permissions and IP restrictions)")
            raise CexAdapterError(f"binance returned HTTP {response.status_code} (code {code})")
        return payload

    def _signed_params(self, api_secret: str, params: dict, *, timestamp_ms: int) -> dict:
        query = {**params, "timestamp": timestamp_ms, "recvWindow": 5000}
        encoded = urlencode(query)
        signature = hmac.new(api_secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        return {**query, "signature": signature}

    def _account(self, api_key: str, api_secret: str) -> dict:
        params = self._signed_params(api_secret, {}, timestamp_ms=self._timestamp_ms())
        return self._get_json("/api/v3/account", params=params, headers={"X-MBX-APIKEY": api_key})

    def validate_credentials(self, api_key: str, api_secret: str, passphrase: str | None = None) -> PermissionCheck:
        payload = self._account(api_key, api_secret)
        if not isinstance(payload, dict) or "balances" not in payload:
            raise CexAdapterError("binance account payload missing balances")
        can_trade = payload.get("canTrade")
        can_withdraw = payload.get("canWithdraw")
        verified = can_trade is not None or can_withdraw is not None
        return PermissionCheck(
            ok=True,
            venue=self.venue,
            can_trade=bool(can_trade) if can_trade is not None else None,
            can_withdraw=bool(can_withdraw) if can_withdraw is not None else None,
            permissions_verified=verified,
            metadata={
                # /sapi/v1/account/apiRestrictions (finer-grained) requires the
                # separate sapi auth scope and is intentionally not called.
                "source": "GET /api/v3/account",
                "account_type": payload.get("accountType"),
                "permissions": list(payload.get("permissions") or []),
                "brokered": bool(payload.get("brokered", False)),
            },
        )

    def _spot_price_usdt(self, symbol: str) -> float | None:
        pair = f"{symbol}USDT"
        try:
            payload = self._get_json("/api/v3/ticker/price", params={"symbol": pair})
        except (CexAdapterError, CexPermissionDenied):
            return None
        try:
            price = float(payload.get("price"))
        except (TypeError, ValueError, AttributeError):
            return None
        return price if price > 0 else None

    def fetch_balances(self, api_key: str, api_secret: str, passphrase: str | None = None) -> list[NormalizedHolding]:
        payload = self._account(api_key, api_secret)
        holdings: list[NormalizedHolding] = []
        for row in payload.get("balances") or []:
            symbol = str(row.get("asset") or "").strip().upper()
            if not symbol:
                continue
            try:
                free = float(row.get("free") or 0)
                locked = float(row.get("locked") or 0)
            except (TypeError, ValueError):
                continue
            quantity = free + locked
            if quantity <= 0:
                continue
            price = 1.0 if symbol in USD_STABLECOINS else self._spot_price_usdt(symbol)
            usd_value = round(quantity * price, 8) if price else None
            holdings.append(
                NormalizedHolding(
                    symbol=symbol,
                    quantity=quantity,
                    usd_value=usd_value,
                    raw={"asset": symbol, "free": free, "locked": locked, "price_usd": price},
                )
            )
        return holdings
