"""Bybit read-only private account adapter.

Signed endpoints used (Bybit V5 auth: ``X-BAPI-SIGN =
hex(HMAC-SHA256(secret, timestamp + api_key + recv_window + query_string))``
with ``X-BAPI-API-KEY`` / ``X-BAPI-TIMESTAMP`` / ``X-BAPI-RECV-WINDOW`` /
``X-BAPI-SIGN-TYPE: 2`` headers):

* ``GET /v5/user/query-api`` — the key's own permission scopes
  (verified read-only intent: ``readOnly`` flag plus ContractTrade/Spot/
  Wallet scopes). If this probe fails we fall back to a successful
  wallet-balance read and record the read-only assumptions as unverified.
* ``GET /v5/account/wallet-balance?accountType=UNIFIED`` — balances. The
  venue's own ``usdValue`` per coin is used for pricing, so no separate
  market-data call is required.

Testnet: ``https://api-testnet.bybit.com`` when ``environment="testnet"``.

No order, trade, or withdrawal endpoint is ever called.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any
from urllib.parse import urlencode

import requests

from packages.data.cex_private.base import (
    CexAdapterError,
    CexPermissionDenied,
    CexPrivateAdapter,
    NormalizedHolding,
    PermissionCheck,
)

_BYBIT_AUTH_CODES = {10003, 10004, 10005, 10008, 10009, 10010, 33004}


class BybitPrivateAdapter(CexPrivateAdapter):
    venue = "bybit"
    production_base_url = "https://api.bybit.com"
    testnet_base_url = "https://api-testnet.bybit.com"

    def _decode(self, response: requests.Response) -> Any:
        try:
            payload = response.json()
        except ValueError as exc:
            raise CexAdapterError(f"bybit returned non-JSON response (HTTP {response.status_code})") from exc
        if response.status_code in {401, 403}:
            raise CexPermissionDenied("bybit rejected the API key/secret (check read-only permissions and IP restrictions)")
        ret_code = payload.get("retCode") if isinstance(payload, dict) else None
        if response.status_code >= 400 or ret_code not in (0, "0", None):
            if ret_code in _BYBIT_AUTH_CODES:
                raise CexPermissionDenied("bybit rejected the API key/secret (check read-only permissions and IP restrictions)")
            raise CexAdapterError(f"bybit returned HTTP {response.status_code} (retCode {ret_code})")
        return payload

    def _signed_headers(self, api_key: str, api_secret: str, query_string: str, *, timestamp_ms: int, recv_window: int = 5000) -> dict:
        prehash = f"{timestamp_ms}{api_key}{recv_window}{query_string}"
        signature = hmac.new(api_secret.encode(), prehash.encode(), hashlib.sha256).hexdigest()
        return {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-SIGN-TYPE": "2",
            "X-BAPI-TIMESTAMP": str(timestamp_ms),
            "X-BAPI-RECV-WINDOW": str(recv_window),
        }

    def _signed_get(self, path: str, api_key: str, api_secret: str, params: dict) -> Any:
        query_string = urlencode(params)
        headers = self._signed_headers(api_key, api_secret, query_string, timestamp_ms=self._timestamp_ms())
        return self._get_json(f"{path}?{query_string}" if query_string else path, headers=headers)

    def _wallet_balance(self, api_key: str, api_secret: str) -> dict:
        return self._signed_get("/v5/account/wallet-balance", api_key, api_secret, {"accountType": "UNIFIED"})

    def validate_credentials(self, api_key: str, api_secret: str, passphrase: str | None = None) -> PermissionCheck:
        try:
            key_info = self._signed_get("/v5/user/query-api", api_key, api_secret, {})
        except (CexAdapterError, CexPermissionDenied):
            key_info = None
        if isinstance(key_info, dict) and isinstance(key_info.get("result"), dict):
            result = key_info["result"]
            permissions = result.get("permissions") or {}
            trade_scopes = {"Order", "SpotTrade", "DerivativesTrade", "OptionsTrade", "Trade"}
            held = {scope for values in permissions.values() if isinstance(values, list) for scope in values}
            can_trade = bool(held & trade_scopes)
            wallet_scopes = permissions.get("Wallet") or []
            can_withdraw = any(scope in {"AccountTransfer", "SubMemberTransfer", "Withdraw"} for scope in wallet_scopes)
            read_only = result.get("readOnly")
            return PermissionCheck(
                ok=True,
                venue=self.venue,
                can_trade=can_trade,
                can_withdraw=can_withdraw,
                permissions_verified=True,
                metadata={
                    "source": "GET /v5/user/query-api",
                    "read_only": bool(read_only == 1) if read_only is not None else None,
                    "note": "read_only flag and trade/withdraw scopes verified against the key itself",
                },
            )
        # Fallback: the balance read succeeded but the venue would not show
        # the key's scopes — record read-only intent as unverified assumptions.
        self._wallet_balance(api_key, api_secret)
        return PermissionCheck(
            ok=True,
            venue=self.venue,
            can_trade=None,
            can_withdraw=None,
            permissions_verified=False,
            metadata={
                "source": "GET /v5/account/wallet-balance",
                "assumed_read_only": True,
                "note": "query-api unavailable; can_trade/can_withdraw recorded as unverified False assumptions",
            },
        )

    def fetch_balances(self, api_key: str, api_secret: str, passphrase: str | None = None) -> list[NormalizedHolding]:
        payload = self._wallet_balance(api_key, api_secret)
        result = payload.get("result") or {}
        holdings: list[NormalizedHolding] = []
        for account in result.get("list") or []:
            account_type = str(account.get("accountType") or "UNIFIED")
            for coin in account.get("coin") or []:
                symbol = str(coin.get("coin") or "").strip().upper()
                if not symbol:
                    continue
                try:
                    quantity = float(coin.get("walletBalance") or 0)
                except (TypeError, ValueError):
                    continue
                if quantity <= 0:
                    continue
                try:
                    usd = float(coin.get("usdValue") or 0)
                except (TypeError, ValueError):
                    usd = 0.0
                usd_value = round(usd, 8) if usd > 0 else None
                holdings.append(
                    NormalizedHolding(
                        symbol=symbol,
                        quantity=quantity,
                        usd_value=usd_value,
                        raw={
                            "coin": symbol,
                            "walletBalance": coin.get("walletBalance"),
                            "usdValue": coin.get("usdValue"),
                            "locked": coin.get("locked"),
                            "accountType": account_type,
                            "price_usd": (usd / quantity) if usd > 0 and quantity > 0 else None,
                        },
                    )
                )
        return holdings
