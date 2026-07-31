from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.api.config import get_settings
from packages.data.provider import DataProvenance, DataSourceHealth, DataSourceProvider, DataSourceStatus, DataSourceSyncResult, ProviderError, SafeHttpClient


class DefiLlamaProvider(DataSourceProvider):
    id = "defillama-free"
    name = "DefiLlama Free"
    category = "defi"

    def __init__(self, base_url: str | None = None, client: SafeHttpClient | None = None, max_items: int = 500):
        settings = get_settings()
        self.base_url = (base_url or settings.defillama_free_base_url).rstrip("/")
        self.client = client or SafeHttpClient(
            allowed_hosts={"api.llama.fi", "stablecoins.llama.fi", "yields.llama.fi"},
            timeout_seconds=settings.provider_http_timeout_seconds,
            max_response_bytes=settings.defillama_max_response_bytes,
        )
        self.max_items = max_items

    def _get(self, path: str) -> Any:
        if path == "/stablecoins":
            url = "https://stablecoins.llama.fi/stablecoins"
        elif path == "/pools":
            url = "https://yields.llama.fi/pools"
        else:
            url = f"{self.base_url}{path}"
        return self.client.request_json("GET", url)

    def health_check(self) -> DataSourceHealth:
        try:
            chains = self._get("/v2/chains")
            if not isinstance(chains, list):
                raise ProviderError("schema_error", "DefiLlama chains response is not a list")
            return DataSourceHealth(DataSourceStatus.HEALTHY, "Free API reachable", details={"proConfigured": bool(get_settings().defillama_pro_key)})
        except ProviderError as exc:
            return DataSourceHealth(DataSourceStatus.RATE_LIMITED if exc.code == "rate_limited" else DataSourceStatus.ERROR, str(exc))

    def sync(self) -> DataSourceSyncResult:
        records: list[dict] = []
        errors: list[str] = []
        endpoints = [
            ("/protocols", self._protocol_metrics),
            ("/v2/chains", self._chain_metrics),
            ("/stablecoins", self._stablecoin_metrics),
            ("/overview/dexs", lambda payload: self._overview_metrics(payload, "dex", "volume")),
            ("/overview/fees", lambda payload: self._overview_metrics(payload, "protocol", "fees")),
            ("/pools", self._yield_metrics),
        ]
        for path, adapter in endpoints:
            try:
                records.extend(adapter(self._get(path))[: self.max_items])
            except Exception as exc:
                errors.append(f"{path}: {str(exc)[:240]}")
        status = DataSourceStatus.ERROR if not records else DataSourceStatus.PARTIAL if errors else DataSourceStatus.HEALTHY
        return DataSourceSyncResult(status=status, records=records, fetched_count=len(records), errors=errors)

    def _metric(self, *, entity_type: str, entity_id: str, entity_name: str, metric_type: str, value: Any, chain: str | None = None, currency: str = "USD", source_path: str) -> dict:
        number = _number(value)
        if number.copy_abs() > Decimal("1e30"):
            raise ProviderError("outlier", f"DefiLlama value is outside accepted range: {entity_id}")
        fetched_at = datetime.now(timezone.utc)
        return {
            "provider": "defillama",
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "entity_name": str(entity_name),
            "chain": chain,
            "metric_type": metric_type,
            "value": number,
            "currency": currency,
            "source_timestamp": None,
            "fetched_at": fetched_at,
            "provenance_json": DataProvenance(provider="defillama", source_url=("https://stablecoins.llama.fi/stablecoins" if source_path == "/stablecoins" else "https://yields.llama.fi/pools" if source_path == "/pools" else f"{self.base_url}{source_path}"), fetched_at=fetched_at).as_dict(),
        }

    def _protocol_metrics(self, payload: Any) -> list[dict]:
        if not isinstance(payload, list):
            raise ProviderError("schema_error", "Protocols response is not a list")
        return [self._metric(entity_type="protocol", entity_id=item.get("slug") or item.get("id"), entity_name=item.get("name"), chain=item.get("chain"), metric_type="tvl", value=item.get("tvl"), source_path="/protocols") for item in payload if item.get("name") and item.get("tvl") is not None]

    def _chain_metrics(self, payload: Any) -> list[dict]:
        if not isinstance(payload, list):
            raise ProviderError("schema_error", "Chains response is not a list")
        return [self._metric(entity_type="chain", entity_id=item.get("name"), entity_name=item.get("name"), chain=item.get("name"), metric_type="tvl", value=item.get("tvl"), source_path="/v2/chains") for item in payload if item.get("name") and item.get("tvl") is not None]

    def _stablecoin_metrics(self, payload: Any) -> list[dict]:
        rows = payload.get("peggedAssets") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ProviderError("schema_error", "Stablecoins response is invalid")
        result = []
        for item in rows:
            circulating = item.get("circulating") or {}
            value = circulating.get("peggedUSD") if isinstance(circulating, dict) else None
            if value is not None:
                result.append(self._metric(entity_type="stablecoin", entity_id=item.get("id"), entity_name=item.get("name"), metric_type="supply", value=value, source_path="/stablecoins"))
        return result

    def _overview_metrics(self, payload: Any, entity_type: str, metric_type: str) -> list[dict]:
        rows = payload.get("protocols") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ProviderError("schema_error", "Overview response is invalid")
        key = "total24h"
        return [self._metric(entity_type=entity_type, entity_id=item.get("slug") or item.get("name"), entity_name=item.get("displayName") or item.get("name"), chain=item.get("chain"), metric_type=metric_type, value=item.get(key), source_path=f"/overview/{'dexs' if metric_type == 'volume' else 'fees'}") for item in rows if item.get(key) is not None]

    def _yield_metrics(self, payload: Any) -> list[dict]:
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ProviderError("schema_error", "Yield pools response is invalid")
        return [self._metric(entity_type="yield_pool", entity_id=item.get("pool"), entity_name=item.get("project") or item.get("symbol"), chain=item.get("chain"), metric_type="apy", value=item.get("apy"), currency="percent", source_path="/pools") for item in rows if item.get("pool") and item.get("apy") is not None]


def _number(value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise InvalidOperation
        return number
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProviderError("invalid_number", "DefiLlama returned an invalid numeric value") from exc
