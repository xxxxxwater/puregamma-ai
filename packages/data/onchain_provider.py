from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from apps.api.config import get_settings
from packages.data.provider import DataProvenance, DataSourceHealth, DataSourceProvider, DataSourceStatus, DataSourceSyncResult, ProviderError, SafeHttpClient


ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
EXPECTED_CHAIN_IDS = {"ethereum": 1, "base": 8453, "arbitrum": 42161, "bsc": 56, "polygon": 137}
ALLOWED_CALL_SELECTORS = {"0x70a08231", "0x313ce567", "0x95d89b41", "0x06fdde03"}


class EVMRPCProvider(DataSourceProvider):
    id = "evm-rpc"
    name = "EVM Public RPC"
    category = "onchain"

    def __init__(self, rpc_urls: dict[str, str] | None = None):
        self.rpc_urls = {chain: url for chain, url in (rpc_urls or get_settings().rpc_urls).items() if url}
        self.clients: dict[str, SafeHttpClient] = {}
        settings = get_settings()
        for chain, url in self.rpc_urls.items():
            host = urlsplit(url).hostname
            if host:
                self.clients[chain] = SafeHttpClient(allowed_hosts={host}, timeout_seconds=settings.provider_http_timeout_seconds, max_response_bytes=1_000_000)

    def _rpc(self, chain: str, method: str, params: list[Any]) -> Any:
        if chain not in self.rpc_urls or chain not in self.clients:
            raise ProviderError("not_connected", f"No RPC configured for {chain}")
        if method not in {"eth_chainId", "eth_blockNumber", "eth_getBlockByNumber", "eth_getBalance", "eth_call"}:
            raise ProviderError("method_not_allowed", "RPC method is not allowlisted")
        payload = self.clients[chain].request_json("POST", self.rpc_urls[chain], json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if not isinstance(payload, dict) or payload.get("error"):
            message = payload.get("error", {}).get("message", "Invalid RPC response") if isinstance(payload, dict) else "Invalid RPC response"
            raise ProviderError("rpc_error", str(message)[:240])
        return payload.get("result")

    def chain_id(self, chain: str) -> int:
        return int(self._rpc(chain, "eth_chainId", []), 16)

    def latest_block(self, chain: str) -> tuple[int, datetime]:
        block_number = int(self._rpc(chain, "eth_blockNumber", []), 16)
        block = self._rpc(chain, "eth_getBlockByNumber", [hex(block_number), False])
        if not isinstance(block, dict) or not block.get("timestamp"):
            raise ProviderError("schema_error", "RPC block response is invalid")
        return block_number, datetime.fromtimestamp(int(block["timestamp"], 16), tz=timezone.utc)

    def native_balance(self, chain: str, address: str, block_tag: str = "latest") -> int:
        if not ADDRESS_RE.fullmatch(address):
            raise ValueError("Invalid EVM address")
        return int(self._rpc(chain, "eth_getBalance", [address, block_tag]), 16)

    def eth_call(self, chain: str, contract: str, data: str, block_tag: str = "latest") -> str:
        if not ADDRESS_RE.fullmatch(contract) or data[:10] not in ALLOWED_CALL_SELECTORS:
            raise ValueError("Contract call is not allowlisted")
        return str(self._rpc(chain, "eth_call", [{"to": contract, "data": data}, block_tag]))

    def health_check(self) -> DataSourceHealth:
        if not self.rpc_urls:
            return DataSourceHealth(DataSourceStatus.NOT_CONNECTED, "No server-side EVM RPC URLs configured")
        successes: list[str] = []
        errors: list[str] = []
        for chain in self.rpc_urls:
            try:
                actual = self.chain_id(chain)
                expected = EXPECTED_CHAIN_IDS.get(chain)
                if expected and actual != expected:
                    raise ProviderError("chain_id_mismatch", f"Expected chain ID {expected}, received {actual}")
                successes.append(chain)
            except Exception as exc:
                errors.append(f"{chain}: {str(exc)[:180]}")
        status = DataSourceStatus.ERROR if not successes else DataSourceStatus.PARTIAL if errors else DataSourceStatus.HEALTHY
        return DataSourceHealth(status, "; ".join(errors) if errors else f"Connected: {', '.join(successes)}")

    def sync(self) -> DataSourceSyncResult:
        records: list[dict] = []
        errors: list[str] = []
        for chain in self.rpc_urls:
            try:
                actual_chain_id = self.chain_id(chain)
                if EXPECTED_CHAIN_IDS.get(chain) != actual_chain_id:
                    raise ProviderError("chain_id_mismatch", f"Unexpected chain ID {actual_chain_id}")
                block_number, source_time = self.latest_block(chain)
                fetched_at = datetime.now(timezone.utc)
                for metric_type, value in (("chain_id", str(actual_chain_id)), ("latest_block", str(block_number))):
                    records.append({
                        "provider": "evm-rpc",
                        "chain": chain,
                        "entity_id": chain,
                        "metric_type": metric_type,
                        "value": value,
                        "block_number": block_number,
                        "source_timestamp": source_time,
                        "fetched_at": fetched_at,
                        "provenance_json": DataProvenance(provider="evm-rpc", source_timestamp=source_time, fetched_at=fetched_at).as_dict(),
                    })
            except Exception as exc:
                errors.append(f"{chain}: {str(exc)[:240]}")
        status = DataSourceStatus.ERROR if not records else DataSourceStatus.PARTIAL if errors else DataSourceStatus.HEALTHY
        return DataSourceSyncResult(status=status, records=records, fetched_count=len(records), errors=errors)


class OnchainProvider(EVMRPCProvider):
    """Backward-compatible read-only on-chain provider."""

    def whale_activity(self, assets: list[str]) -> dict[str, str]:
        raise ProviderError("historical_index_unavailable", "Historical transfer scanning requires a configured indexer or subgraph")
