from __future__ import annotations

import os
from datetime import datetime, timezone

from packages.data.base import MarketQuote, asset_type_for


class NasdaqDataLinkProvider:
    """Official Nasdaq Data Link real-time/delayed equity snapshot adapter."""

    provider_name = "nasdaq"

    def __init__(
        self,
        base_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ):
        self.base_url = (base_url or os.getenv("NASDAQ_DATA_LINK_BASE_URL", "")).rstrip("/")
        self.client_id = client_id or os.getenv("NASDAQ_DATA_LINK_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("NASDAQ_DATA_LINK_CLIENT_SECRET", "")
        self.source = os.getenv("NASDAQ_DATA_LINK_SOURCE", "nasdaq").lower()
        self.offset = os.getenv("NASDAQ_DATA_LINK_OFFSET", "delayed").lower()
        self._session = None
        self._access_token = ""

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.client_id and self.client_secret)

    def _client(self):
        if self._session is None:
            import requests

            self._session = requests.Session()
        return self._session

    def _token(self) -> str:
        if self._access_token:
            return self._access_token
        response = self._client().post(
            f"{self.base_url}/v1/auth/token",
            json={"client_id": self.client_id, "client_secret": self.client_secret},
            timeout=10,
        )
        response.raise_for_status()
        self._access_token = str(response.json()["access_token"])
        return self._access_token

    def get_quote(self, symbol: str) -> MarketQuote | None:
        if not self.enabled:
            return None
        normalized = symbol.upper()
        response = self._client().get(
            f"{self.base_url}/v1/{self.source}/{self.offset}/equities/snapshot/{normalized}",
            headers={"Authorization": f"Bearer {self._token()}"},
            timeout=10,
        )
        if response.status_code == 401:
            self._access_token = ""
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            return None
        row = payload[0]
        price = float(row.get("lastSale") or row.get("lastTrade") or row.get("close") or 0)
        if price <= 0:
            return None
        timestamp = datetime.now(timezone.utc)
        raw_timestamp = row.get("timestamp")
        if raw_timestamp:
            try:
                timestamp = datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        volume = float(row.get("dollarVolume") or 0)
        if not volume:
            volume = float(row.get("volume") or 0) * price
        return MarketQuote(
            symbol=normalized,
            price=price,
            volume_24h=volume,
            market_cap=0.0,
            funding_rate=0.0,
            open_interest=0.0,
            volatility=0.0,
            liquidation_estimate=0.0,
            sentiment_score=0.5,
            timestamp=timestamp.astimezone(timezone.utc),
            source="nasdaq",
            source_symbol=f"NASDAQ:{normalized}",
            change_24h=float(row["percentChange"]) if row.get("percentChange") is not None else None,
            is_realtime=self.offset == "realtime",
            asset_type=asset_type_for(normalized),
            open_interest_usd=None,
        )

