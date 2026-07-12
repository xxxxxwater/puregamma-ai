from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx


class DeribitUnavailable(RuntimeError):
    pass


class DeribitPublicProvider:
    provider_name = "deribit_public"

    def __init__(self, base_url: str, timeout: float = 8.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def option_chain(self, currency: str, detail_limit: int = 12) -> dict:
        currency = currency.upper()
        if currency not in {"BTC", "ETH"}:
            raise ValueError("Deribit V4 currently supports BTC and ETH options")
        instruments = self._get(
            "public/get_instruments",
            {"currency": currency, "kind": "option", "expired": "false"},
        )
        summaries = self._get(
            "public/get_book_summary_by_currency",
            {"currency": currency, "kind": "option"},
        )
        metadata = {item["instrument_name"]: item for item in instruments}
        rows = []
        for item in summaries:
            instrument = metadata.get(item.get("instrument_name"), {})
            if not instrument:
                continue
            rows.append(self._normalize(instrument, item))
        rows.sort(
            key=lambda row: row["volume_24h"] + row["open_interest"], reverse=True
        )
        detailed_rows = rows[: max(0, min(detail_limit, 20))]
        with ThreadPoolExecutor(
            max_workers=min(6, len(detailed_rows) or 1)
        ) as executor:
            list(executor.map(self._enrich, detailed_rows))
        return {
            "provider": self.provider_name,
            "status": "HEALTHY",
            "currency": currency,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "instruments": rows,
            "source_url": f"{self.base_url}/api/v2/public/get_book_summary_by_currency",
            "live_trading": False,
        }

    def _enrich(self, row: dict) -> None:
        try:
            detail = self._get(
                "public/get_order_book", {"instrument_name": row["instrument"]}
            )
            row.update(
                greeks=detail.get("greeks", {}),
                mark_iv=detail.get("mark_iv", row.get("mark_iv")),
                bid_iv=detail.get("bid_iv"),
                ask_iv=detail.get("ask_iv"),
                index_price=detail.get("index_price"),
                timestamp=self._time(detail.get("timestamp")),
            )
        except DeribitUnavailable:
            row["detail_status"] = "DEGRADED"

    def _get(self, method: str, params: dict[str, Any]) -> Any:
        try:
            response = httpx.get(
                f"{self.base_url}/api/v2/{method}",
                params=params,
                timeout=self.timeout,
                headers={"User-Agent": "PureGamma AI/0.4 read-only-options"},
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                raise DeribitUnavailable(str(payload["error"])[:240])
            return payload.get("result", [])
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise DeribitUnavailable(
                f"Deribit public API unavailable: {str(exc)[:200]}"
            ) from exc

    @staticmethod
    def _time(value: int | float | None) -> str:
        if not value:
            return datetime.now(timezone.utc).isoformat()
        return datetime.fromtimestamp(float(value) / 1000, timezone.utc).isoformat()

    def _normalize(self, instrument: dict, summary: dict) -> dict:
        bid = summary.get("bid_price")
        ask = summary.get("ask_price")
        mid = summary.get("mid_price")
        spread = None
        if bid is not None and ask is not None and mid:
            spread = max(0.0, (float(ask) - float(bid)) / float(mid))
        return {
            "instrument": instrument["instrument_name"],
            "underlying": instrument.get("base_currency"),
            "option_type": instrument.get("option_type"),
            "strike": float(instrument.get("strike", 0)),
            "expiry": self._time(instrument.get("expiration_timestamp")),
            "contract_size": float(instrument.get("contract_size", 1)),
            "min_trade_amount": float(instrument.get("min_trade_amount", 0)),
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "mark_price": summary.get("mark_price"),
            "mark_iv": summary.get("mark_iv"),
            "underlying_price": summary.get("underlying_price"),
            "volume_24h": float(summary.get("volume", 0) or 0),
            "open_interest": float(summary.get("open_interest", 0) or 0),
            "spread_pct": spread,
            "greeks": {},
            "timestamp": self._time(summary.get("creation_timestamp")),
            "detail_status": "PENDING",
        }
