from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import GatewayModel, GatewayPriceRevision, GatewayProvider
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


def configured_providers() -> dict[str, dict[str, Any]]:
    """Return only the data-only provider records from the configured catalog."""
    catalog = _load_catalog(get_settings().gateway_catalog_path)
    providers = catalog.get("providers") or {}
    if not isinstance(providers, dict):
        return {}
    return {str(name): value for name, value in providers.items() if isinstance(value, dict)}


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


def _decimal(value: Any) -> Decimal | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount >= 0 else None


def _format_decimal(value: Decimal) -> str:
    """Produce a stable, human-readable decimal without scientific notation."""
    return format(value.normalize(), "f") if value else "0"


def _price_items(raw_prices: dict[str, Any], currency: str) -> dict[str, dict[str, str]]:
    """Normalize a provider's data-only price map for safe public display."""
    normalized: dict[str, dict[str, str]] = {}
    currency_key = currency.lower()
    for raw_key, raw_value in (raw_prices or {}).items():
        key = str(raw_key).strip().lower()
        if not key or not isinstance(raw_value, dict):
            continue
        amount = _decimal(raw_value.get(currency_key, raw_value.get("amount", raw_value.get("price"))))
        if amount is None:
            continue
        item = {
            "amount": _format_decimal(amount),
            "unit": str(raw_value.get("unit") or "per_million_tokens"),
        }
        if raw_value.get("description"):
            item["description"] = str(raw_value["description"])
        normalized[key] = item
    return normalized


def _with_markup(prices: dict[str, dict[str, str]], markup_bps: int) -> dict[str, dict[str, str]]:
    multiplier = Decimal("1") + Decimal(markup_bps) / Decimal("10000")
    final: dict[str, dict[str, str]] = {}
    for key, item in prices.items():
        amount = _decimal(item.get("amount"))
        if amount is None:
            continue
        final[key] = {
            **item,
            "amount": _format_decimal((amount * multiplier).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)),
        }
    return final


def _catalog_price_snapshot(model: dict[str, Any], markup_bps: int) -> dict[str, Any] | None:
    """Build a non-billable display quote directly from the reviewed catalog.

    `official_prices` is USD and may be used by the pricing-sync flow.  A
    provider can instead supply `display_prices` in another official currency;
    those values are deliberately presentation-only until a billing policy is
    approved.
    """
    raw_official = model.get("official_prices")
    if isinstance(raw_official, dict) and raw_official:
        official = _price_items(raw_official, "USD")
        if official:
            return {
                "currency": "USD",
                "official": official,
                "final": _with_markup(official, markup_bps),
                "status": "catalog_unapproved",
            }
    raw_display = model.get("display_prices")
    if isinstance(raw_display, dict):
        currency = str(raw_display.get("currency") or "USD").upper()
        official = _price_items(raw_display, currency)
        if official:
            return {
                "currency": currency,
                "official": official,
                "final": _with_markup(official, markup_bps),
                "status": "requires_currency_policy" if currency != "USD" else "catalog_unapproved",
            }
    return None


def _revision_price_snapshot(revision: GatewayPriceRevision) -> dict[str, Any] | None:
    currency = str(revision.currency or "USD").upper()
    official = _price_items(dict(revision.official_prices_json or {}), currency)
    final = _price_items(dict(revision.final_prices_json or {}), currency)
    if not official or not final:
        return None
    return {
        "currency": currency,
        "official": official,
        "final": final,
        "status": "active" if revision.status == "active" else revision.status,
    }


def public_model_catalog(db: Session, *, markup_bps: int) -> list[dict[str, Any]]:
    """Return the public, secret-free catalog used by the product API page.

    Active, administrator-approved database pricing always wins.  If a model
    has not been activated yet, the endpoint may expose a clearly labelled
    catalog quote so customers can see the official source and the current
    markup without treating that quote as billable availability.
    """
    records = {
        model.public_id: (model, provider, db.get(GatewayPriceRevision, model.active_pricing_id) if model.active_pricing_id else None)
        for model, provider in db.query(GatewayModel, GatewayProvider)
        .join(GatewayProvider, GatewayModel.provider_id == GatewayProvider.id)
        .all()
    }
    result: list[dict[str, Any]] = []
    for provider_name, provider in configured_providers().items():
        provider_display_name = str(provider.get("display_name") or provider_name)
        raw_models = provider.get("models") or []
        if not isinstance(raw_models, list):
            continue
        for raw_model in raw_models:
            if not isinstance(raw_model, dict) or not raw_model.get("public_id"):
                continue
            public_id = str(raw_model["public_id"])
            database_model, database_provider, revision = records.get(public_id, (None, None, None))
            capabilities = dict(raw_model.get("capabilities") or {})
            metadata = dict(raw_model.get("metadata") or {})
            snapshot = _revision_price_snapshot(revision) if revision else None
            if snapshot is None:
                snapshot = _catalog_price_snapshot(raw_model, markup_bps)
            if database_model and database_provider and revision and revision.status == "active" and database_model.status == "active" and database_provider.enabled:
                availability = "available"
            elif database_model and database_model.status == "pending":
                availability = "pending_approval"
            elif database_provider and not database_provider.enabled:
                availability = "provider_disabled"
            else:
                availability = "setup_required"
            result.append(
                {
                    "id": public_id,
                    "display_name": str(raw_model.get("display_name") or public_id),
                    "provider": provider_name,
                    "provider_display_name": provider_display_name,
                    "provider_model_id": str(raw_model.get("provider_model_id") or public_id),
                    "capabilities": capabilities,
                    "metadata": {
                        key: value
                        for key, value in metadata.items()
                        if key in {"billing_region", "pricing_status", "official_currency", "reasoning_priced_as"}
                    },
                    "availability": availability,
                    "pricing": snapshot,
                    "source_reference": str(raw_model.get("source_reference")) if raw_model.get("source_reference") else None,
                }
            )
    return result
