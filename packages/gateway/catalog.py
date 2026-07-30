from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from apps.api.config import get_settings
from packages.gateway.contracts import ProviderModelMetadata


ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=4)
def _load_catalog(path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return {"providers": {}}
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return raw if isinstance(raw, dict) else {"providers": {}}


def clear_catalog_cache() -> None:
    _load_catalog.cache_clear()


def provider_catalog(name: str) -> dict[str, Any]:
    catalog = _load_catalog(get_settings().gateway_catalog_path)
    providers = catalog.get("providers") or {}
    value = providers.get(name, {}) if isinstance(providers, dict) else {}
    return value if isinstance(value, dict) else {}


def provider_models(name: str) -> list[ProviderModelMetadata]:
    config = provider_catalog(name)
    models = config.get("models") or []
    result: list[ProviderModelMetadata] = []
    for item in models:
        if not isinstance(item, dict) or not item.get("public_id") or not item.get("provider_model_id"):
            continue
        result.append(
            ProviderModelMetadata(
                public_id=str(item["public_id"]),
                provider_model_id=str(item["provider_model_id"]),
                display_name=str(item.get("display_name") or item["public_id"]),
                capabilities=dict(item.get("capabilities") or {}),
                metadata=dict(item.get("metadata") or {}),
                # Prices are intentionally data, not source code. The operator
                # can maintain this official catalog or use a provider API.
                official_prices=dict(item.get("official_prices") or {}),
                source_reference=str(item.get("source_reference")) if item.get("source_reference") else None,
            )
        )
    return result
