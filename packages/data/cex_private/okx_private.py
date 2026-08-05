"""OKX read-only private account adapter.

Signed endpoint used: ``GET /api/v5/account/balance`` with the OKX v5 auth
scheme: ``OK-ACCESS-SIGN = base64(HMAC-SHA256(secret, timestamp + "GET" +
request_path))`` plus ``OK-ACCESS-KEY`` / ``OK-ACCESS-TIMESTAMP`` /
``OK-ACCESS-PASSPHRASE`` headers.

OKX does not expose the key's own trade/withdraw scopes on a main-account
read endpoint (``/api/v5/users/subaccount/apikey`` only covers sub-accounts),
so permissions are inferred from the successful read and recorded as
UNVERIFIED ``can_trade=False`` / ``can_withdraw=False`` assumptions — the
service layer never places orders regardless.

USD values come from the venue's own ``eqUsd`` field on each currency detail,
so no separate market-data call is required.

Demo trading: ``environment="testnet"`` adds the documented
``x-simulated-trading: 1`` header against the production base URL.

No order, trade, or withdrawal endpoint is ever called.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any

import requests

from packages.data.cex_private.base import (
    CexAdapterError,
    CexPermissionDenied,
    CexPrivateAdapter,
    NormalizedHolding,
    PermissionCheck,
)


class OkxPrivateAdapter(CexPrivateAdapter):
    venue = "okx"
    production_base_url = "https://www.okx.com"
    testnet_base_url = None  # demo trading reuses production URL + simulated header

    @property
    def _supports_simulated_header(self) -> bool:
        return True

    def _timestamp_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _decode(self, response: requests.Response) -> Any:
        try:
            payload = response.json()
        except ValueError as exc:
            raise CexAdapterError(f"okx returned non-JSON response (HTTP {response.status_code})") from exc
        if response.status_code in {401, 403}:
            raise CexPermissionDenied("okx rejected the API key/secret/passphrase (check read-only permissions and IP restrictions)")
        if response.status_code >= 400:
            raise CexAdapterError(f"okx returned HTTP {response.status_code}")
        code = str(payload.get("code") or "") if isinstance(payload, dict) else ""
        if code != "0":
            if code in {"50100", "50101", "50102", "50104", "50105", "50106", "50107", "50111", "50112", "50113", "50114", "50115"}:
                raise CexPermissionDenied("okx rejected the API key/secret/passphrase (check read-only permissions and IP restrictions)")
            raise CexAdapterError(f"okx returned error code {code}")
        return payload

    def _signed_headers(self, api_key: str, api_secret: str, passphrase: str, request_path: str, *, timestamp_iso: str) -> dict:
        prehash = f"{timestamp_iso}GET{request_path}"
        signature = base64.b64encode(hmac.new(api_secret.encode(), prehash.encode(), hashlib.sha256).digest()).decode()
        headers = {
            "OK-ACCESS-KEY": api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp_iso,
            "OK-ACCESS-PASSPHRASE": passphrase,
            "Content-Type": "application/json",
        }
        if self.environment == "testnet":
            headers["x-simulated-trading"] = "1"
        return headers

    def _balance(self, api_key: str, api_secret: str, passphrase: str) -> dict:
        request_path = "/api/v5/account/balance"
        headers = self._signed_headers(api_key, api_secret, passphrase, request_path, timestamp_iso=self._timestamp_iso())
        return self._get_json(request_path, headers=headers)

    def validate_credentials(self, api_key: str, api_secret: str, passphrase: str | None = None) -> PermissionCheck:
        if not passphrase:
            raise CexPermissionDenied("okx read-only keys require the API passphrase")
        payload = self._balance(api_key, api_secret, passphrase)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise CexAdapterError("okx balance payload missing data")
        return PermissionCheck(
            ok=True,
            venue=self.venue,
            # Main-account keys do not expose their own scopes on a read
            # endpoint; record the read-only intent as unverified assumptions.
            can_trade=None,
            can_withdraw=None,
            permissions_verified=False,
            metadata={
                "source": "GET /api/v5/account/balance",
                "assumed_read_only": True,
                "note": "okx does not expose main-account key scopes on read endpoints; can_trade/can_withdraw recorded as unverified False assumptions",
            },
        )

    def fetch_balances(self, api_key: str, api_secret: str, passphrase: str | None = None) -> list[NormalizedHolding]:
        if not passphrase:
            raise CexPermissionDenied("okx read-only keys require the API passphrase")
        payload = self._balance(api_key, api_secret, passphrase)
        holdings: list[NormalizedHolding] = []
        for account in payload.get("data") or []:
            for detail in account.get("details") or []:
                symbol = str(detail.get("ccy") or "").strip().upper()
                if not symbol:
                    continue
                try:
                    equity = float(detail.get("eq") or 0)
                except (TypeError, ValueError):
                    continue
                if equity <= 0:
                    try:
                        equity = float(detail.get("availBal") or 0) + float(detail.get("frozenBal") or 0)
                    except (TypeError, ValueError):
                        continue
                if equity <= 0:
                    continue
                try:
                    eq_usd = float(detail.get("eqUsd") or 0)
                except (TypeError, ValueError):
                    eq_usd = 0.0
                usd_value = round(eq_usd, 8) if eq_usd > 0 else None
                holdings.append(
                    NormalizedHolding(
                        symbol=symbol,
                        quantity=equity,
                        usd_value=usd_value,
                        raw={
                            "ccy": symbol,
                            "availBal": detail.get("availBal"),
                            "frozenBal": detail.get("frozenBal"),
                            "eq": detail.get("eq"),
                            "eqUsd": detail.get("eqUsd"),
                            "price_usd": (eq_usd / equity) if eq_usd > 0 and equity > 0 else None,
                        },
                    )
                )
        return holdings
