from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx


class EquityOptionsUnavailable(RuntimeError):
    pass


class PolygonOptionsProvider:
    """US equity option chains via Polygon.io (needs POLYGON_API_KEY)."""

    provider_name = "polygon_options"

    def __init__(self, api_key: str, base_url: str = "https://api.polygon.io", timeout: float = 10.0):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def option_chain(self, ticker: str, detail_limit: int = 12) -> dict:
        """Return a chain with the same schema as the Deribit provider.

        Contracts are resolved through /v3/reference/options/contracts and
        snapshots through /v3/snapshot/options/{underlying}/{option_symbol}.
        """
        ticker = ticker.upper()
        if not self.api_key:
            raise EquityOptionsUnavailable(
                "POLYGON_API_KEY is not configured; equity option surfaces are unavailable"
            )
        contracts = self._get(
            "v3/reference/options/contracts",
            {
                "underlying_ticker": ticker,
                "status": "active",
                "expiration_date.gte": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "limit": 1000,
            },
        )
        if not contracts:
            raise EquityOptionsUnavailable(f"No active option contracts for {ticker}")
        rows = []
        for contract in contracts:
            symbol = contract.get("ticker") or contract.get("symbol")
            if not symbol:
                continue
            try:
                snapshot = self._snapshot(ticker, symbol)
            except EquityOptionsUnavailable:
                continue
            row = self._normalize(contract, snapshot)
            if row:
                rows.append(row)
        if not rows:
            raise EquityOptionsUnavailable(f"No option snapshots available for {ticker}")
        rows.sort(key=lambda row: row["volume_24h"] + row["open_interest"], reverse=True)
        return {
            "provider": self.provider_name,
            "status": "HEALTHY",
            "currency": ticker,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "instruments": rows,
            "source_url": f"{self.base_url}/v3/reference/options/contracts?underlying_ticker={ticker}",
            "live_trading": False,
        }

    def _snapshot(self, underlying: str, option_symbol: str) -> dict:
        try:
            payload = self._get(f"v3/snapshot/options/{underlying}/{option_symbol}", {})
        except EquityOptionsUnavailable:
            raise
        if not isinstance(payload, dict):
            raise EquityOptionsUnavailable(f"Malformed snapshot for {option_symbol}")
        result = payload.get("results", payload)
        return result if isinstance(result, dict) else {}

    def _normalize(self, contract: dict, snapshot: dict) -> dict | None:
        details = snapshot.get("greek") or {}
        strike = contract.get("strike_price")
        expiry = contract.get("expiration_date")
        if strike is None or not expiry:
            return None
        bid = snapshot.get("bid")
        ask = snapshot.get("ask")
        mid = snapshot.get("midpoint")
        spread = None
        if bid is not None and ask is not None and mid:
            spread = max(0.0, (float(ask) - float(bid)) / float(mid))
        underlying = snapshot.get("underlying_asset", {}).get("price")
        if not underlying:
            underlying = snapshot.get("last_quote", {}).get("underlying_price")
        return {
            "instrument": contract.get("ticker") or contract.get("symbol"),
            "underlying": contract.get("underlying_ticker"),
            "option_type": "call" if str(contract.get("contract_type", "")).lower() == "call" else "put",
            "strike": float(strike),
            "expiry": f"{expiry}T23:59:59+00:00",
            "contract_size": float(contract.get("shares_per_contract") or 100),
            "min_trade_amount": 0,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "mark_price": details.get("iv") if snapshot.get("implied_volatility") is None else snapshot.get("implied_volatility"),
            "mark_iv": snapshot.get("implied_volatility") or details.get("iv"),
            "underlying_price": underlying,
            "volume_24h": float(snapshot.get("day", {}).get("volume") or 0),
            "open_interest": float(snapshot.get("open_interest") or 0),
            "spread_pct": spread,
            "greeks": {
                "delta": float(details.get("delta") or 0),
                "gamma": float(details.get("gamma") or 0),
                "theta": float(details.get("theta") or 0),
                "vega": float(details.get("vega") or 0),
            },
            "timestamp": snapshot.get("updated") or datetime.now(timezone.utc).isoformat(),
            "detail_status": "HEALTHY",
        }

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        try:
            response = httpx.get(
                f"{self.base_url}/{path}",
                params={**params, "apiKey": self.api_key},
                timeout=self.timeout,
                headers={"User-Agent": "PureGamma AI/0.4 read-only-options"},
            )
            response.raise_for_status()
            payload = response.json()
            status = payload.get("status")
            if status and status not in {"OK", "DELAYED"}:
                raise EquityOptionsUnavailable(str(payload.get("message") or status)[:240])
            return payload.get("results", payload)
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise EquityOptionsUnavailable(
                f"Polygon options API unavailable: {str(exc)[:200]}"
            ) from exc
