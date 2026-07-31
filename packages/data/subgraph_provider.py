from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from packages.data.provider import DataSourceHealth, DataSourceProvider, DataSourceStatus, DataSourceSyncResult, ProviderError, SafeHttpClient


ALLOWED_QUERIES = {
    "pools": "query Pools($first: Int!, $skip: Int!) { pools(first: $first, skip: $skip, orderBy: totalValueLockedUSD, orderDirection: desc) { id totalValueLockedUSD volumeUSD txCount } }",
    "markets": "query Markets($first: Int!, $skip: Int!) { markets(first: $first, skip: $skip) { id totalValueLockedUSD totalBorrowBalanceUSD } }",
}


@dataclass(frozen=True)
class SubgraphConfig:
    id: str
    name: str
    protocol: str
    chain: str
    endpoint_env: str
    entity_type: str
    enabled: bool = False

    @property
    def endpoint(self) -> str:
        return os.getenv(self.endpoint_env, "")


class SubgraphProvider(DataSourceProvider):
    id = "the-graph"
    name = "The Graph / Subgraphs"
    category = "onchain"

    def __init__(self, registry_path: str = "config/subgraphs.yaml"):
        raw = yaml.safe_load(Path(registry_path).read_text()) or {}
        self.registry = [SubgraphConfig(**item) for item in raw.get("subgraphs", [])]

    def _enabled(self) -> list[SubgraphConfig]:
        return [item for item in self.registry if item.enabled and item.endpoint]

    def _query(self, config: SubgraphConfig, first: int = 100, skip: int = 0) -> list[dict]:
        query = ALLOWED_QUERIES.get(config.entity_type)
        if not query:
            raise ProviderError("query_not_allowed", "Subgraph entity type is not allowlisted")
        host = urlsplit(config.endpoint).hostname
        if not host:
            raise ProviderError("invalid_endpoint", "Subgraph endpoint is invalid")
        payload = SafeHttpClient(allowed_hosts={host}, max_response_bytes=2_000_000).request_json("POST", config.endpoint, json={"query": query, "variables": {"first": min(first, 250), "skip": max(skip, 0)}})
        if payload.get("errors"):
            raise ProviderError("graphql_error", str(payload["errors"][0].get("message", "GraphQL error"))[:240])
        rows = payload.get("data", {}).get(config.entity_type)
        if not isinstance(rows, list):
            raise ProviderError("schema_error", "Subgraph returned an invalid result")
        return rows

    def health_check(self) -> DataSourceHealth:
        enabled = self._enabled()
        if not enabled:
            return DataSourceHealth(DataSourceStatus.NOT_CONNECTED, "No reviewed subgraph endpoint enabled")
        successes = 0
        errors = []
        for config in enabled:
            try:
                self._query(config, first=1)
                successes += 1
            except Exception as exc:
                errors.append(f"{config.name}: {str(exc)[:180]}")
        status = DataSourceStatus.ERROR if not successes else DataSourceStatus.PARTIAL if errors else DataSourceStatus.HEALTHY
        return DataSourceHealth(status, "; ".join(errors) if errors else f"{successes} subgraphs reachable")

    def sync(self) -> DataSourceSyncResult:
        records = []
        errors = []
        for config in self._enabled():
            try:
                for row in self._query(config):
                    records.append({"config": config, "data": row})
            except Exception as exc:
                errors.append(f"{config.name}: {str(exc)[:240]}")
        status = DataSourceStatus.NOT_CONNECTED if not self._enabled() else DataSourceStatus.ERROR if not records else DataSourceStatus.PARTIAL if errors else DataSourceStatus.HEALTHY
        return DataSourceSyncResult(status=status, records=records, fetched_count=len(records), errors=errors)
