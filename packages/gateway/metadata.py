from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import (
    GatewayModel,
    GatewayPriceRevision,
    GatewayPricingPolicy,
    GatewayProvider,
    GatewayProviderSync,
    GatewaySecurityEvent,
)
from packages.gateway.catalog import provider_catalog
from packages.gateway.pricing import final_prices, normalize_official_prices
from packages.gateway.registry import provider_registry


def _now() -> datetime:
    return datetime.now(timezone.utc)


def pricing_policy(db: Session) -> GatewayPricingPolicy:
    row = db.query(GatewayPricingPolicy).filter_by(name="default").one_or_none()
    if row is None:
        row = GatewayPricingPolicy(name="default", markup_bps=3000, active=True)
        db.add(row)
        db.flush()
    return row


def bootstrap_gateway_catalog(db: Session) -> dict[str, int]:
    """Create only configured providers/models. They remain pending until approved."""
    settings = get_settings()
    pricing_policy(db)
    added_providers = added_models = 0
    for provider_name in provider_registry.names():
        catalog = provider_catalog(provider_name)
        if not catalog:
            continue
        adapter = provider_registry.create(provider_name, settings, catalog)
        provider = db.query(GatewayProvider).filter_by(name=provider_name).one_or_none()
        if provider is None:
            provider = GatewayProvider(
                name=provider_name,
                display_name=str(catalog.get("display_name") or provider_name),
                base_url=adapter.base_url,
                metadata_json=catalog,
            )
            db.add(provider)
            db.flush()
            added_providers += 1
        else:
            provider.display_name = str(catalog.get("display_name") or provider.display_name)
            provider.base_url = adapter.base_url
            provider.metadata_json = catalog
        for item in adapter.get_models():
            model = db.query(GatewayModel).filter_by(public_id=item.public_id).one_or_none()
            if model is None:
                db.add(
                    GatewayModel(
                        public_id=item.public_id,
                        provider_id=provider.id,
                        provider_model_id=item.provider_model_id,
                        display_name=item.display_name,
                        status="pending",
                        capabilities_json=item.capabilities,
                        metadata_json=item.metadata,
                    )
                )
                added_models += 1
            else:
                model.provider_id = provider.id
                model.provider_model_id = item.provider_model_id
                model.display_name = item.display_name
                model.capabilities_json = item.capabilities
                model.metadata_json = item.metadata
                model.last_synced_at = _now()
    db.commit()
    return {"providers": added_providers, "models": added_models}


def _source_hash(metadata: dict[str, Any]) -> str:
    raw = json.dumps(metadata, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sync_provider_metadata(
    db: Session,
    provider_name: str,
    *,
    triggered_by: str = "scheduler",
    triggered_by_user_id: str | None = None,
) -> GatewayProviderSync:
    bootstrap_gateway_catalog(db)
    provider = db.query(GatewayProvider).filter_by(name=provider_name).one_or_none()
    if provider is None:
        raise ValueError("GATEWAY_PROVIDER_NOT_FOUND")
    sync = GatewayProviderSync(
        provider_id=provider.id,
        status="running",
        triggered_by=triggered_by,
        triggered_by_user_id=triggered_by_user_id,
    )
    db.add(sync)
    db.flush()
    sync_id = sync.id
    try:
        policy = pricing_policy(db)
        adapter = provider_registry.create(provider.name, get_settings(), provider.metadata_json)
        models = {item.public_id: item for item in adapter.get_models()}
        prices = {item.public_id: item for item in adapter.get_pricing()}
        created_revisions = 0
        for public_id, item in models.items():
            model = db.query(GatewayModel).filter_by(public_id=public_id).one_or_none()
            if model is None:
                model = GatewayModel(
                    public_id=item.public_id,
                    provider_id=provider.id,
                    provider_model_id=item.provider_model_id,
                    display_name=item.display_name,
                    status="pending",
                )
                db.add(model)
                db.flush()
            model.provider_id = provider.id
            model.provider_model_id = item.provider_model_id
            model.display_name = item.display_name
            model.capabilities_json = item.capabilities
            model.metadata_json = item.metadata
            model.last_synced_at = _now()
            pricing_item = prices.get(public_id)
            if not pricing_item or not pricing_item.official_prices:
                continue
            official = normalize_official_prices(pricing_item.official_prices)
            digest = _source_hash({"model": public_id, "prices": official, "source": pricing_item.source_reference})
            existing = (
                db.query(GatewayPriceRevision)
                .filter_by(model_id=model.id, source_hash=digest)
                .order_by(GatewayPriceRevision.synced_at.desc())
                .first()
            )
            if existing:
                continue
            db.add(
                GatewayPriceRevision(
                    model_id=model.id,
                    status="pending",
                    markup_bps=policy.markup_bps,
                    official_prices_json=official,
                    final_prices_json=final_prices(official, policy.markup_bps),
                    source_type="config",
                    source_reference=pricing_item.source_reference,
                    source_hash=digest,
                )
            )
            created_revisions += 1
        sync.models_seen = len(models)
        sync.prices_seen = len(prices)
        sync.status = "pending_review" if created_revisions else "completed"
        sync.summary_json = {"new_price_revisions": created_revisions, "models": sorted(models)}
        sync.completed_at = _now()
        if created_revisions:
            db.add(
                GatewaySecurityEvent(
                    event_type="pricing_update_pending",
                    severity="info",
                    metadata_json={"provider": provider.name, "sync_id": sync.id, "revisions": created_revisions},
                )
            )
        db.commit()
        return sync
    except Exception as exc:
        db.rollback()
        sync = db.get(GatewayProviderSync, sync_id)
        if sync:
            sync.status = "failed"
            sync.error_message = type(exc).__name__
            sync.completed_at = _now()
            db.commit()
        raise


def sync_all_provider_metadata(db: Session, *, triggered_by: str = "scheduler") -> list[GatewayProviderSync]:
    bootstrap_gateway_catalog(db)
    names = [row.name for row in db.query(GatewayProvider).filter_by(enabled=True).order_by(GatewayProvider.name).all()]
    return [sync_provider_metadata(db, name, triggered_by=triggered_by) for name in names]


def health_check_providers(db: Session) -> list[dict[str, Any]]:
    """Run the single provider health contract and persist only safe metadata."""
    rows = db.query(GatewayProvider).filter_by(enabled=True).order_by(GatewayProvider.name).all()
    results: list[dict[str, Any]] = []
    for provider in rows:
        adapter = provider_registry.create(provider.name, get_settings(), dict(provider.metadata_json or {}))
        result = adapter.health_check()
        healthy = bool(result.get("healthy"))
        provider.last_health_at = _now()
        provider.health_status = "healthy" if healthy else "unhealthy"
        provider.last_error = str(result.get("error") or "")[:500] or None
        provider.consecutive_failures = 0 if healthy else int(provider.consecutive_failures or 0) + 1
        results.append(
            {
                "provider": provider.name,
                "healthy": healthy,
                "status": provider.health_status,
                "error": provider.last_error,
            }
        )
    db.commit()
    return results


def approve_price_revision(db: Session, revision_id: str, admin_user_id: str) -> GatewayPriceRevision:
    revision = db.get(GatewayPriceRevision, revision_id)
    if not revision or revision.status != "pending":
        raise ValueError("GATEWAY_PRICE_REVISION_NOT_PENDING")
    model = db.get(GatewayModel, revision.model_id)
    if not model:
        raise ValueError("GATEWAY_MODEL_NOT_FOUND")
    if model.active_pricing_id:
        previous = db.get(GatewayPriceRevision, model.active_pricing_id)
        if previous and previous.status == "active":
            previous.status = "superseded"
    revision.status = "active"
    revision.approved_at = _now()
    revision.approved_by_user_id = admin_user_id
    model.active_pricing_id = revision.id
    model.status = "active"
    db.commit()
    db.refresh(revision)
    return revision


def set_default_markup(db: Session, markup_bps: int, admin_user_id: str) -> GatewayPricingPolicy:
    if markup_bps < 0 or markup_bps > 100_000:
        raise ValueError("GATEWAY_MARKUP_INVALID")
    policy = pricing_policy(db)
    policy.markup_bps = markup_bps
    policy.updated_by_user_id = admin_user_id
    active_models = db.query(GatewayModel).filter(GatewayModel.active_pricing_id.is_not(None)).all()
    for model in active_models:
        current = db.get(GatewayPriceRevision, model.active_pricing_id)
        if not current:
            continue
        current.status = "superseded"
        replacement = GatewayPriceRevision(
            model_id=model.id,
            status="active",
            markup_bps=markup_bps,
            official_prices_json=current.official_prices_json,
            final_prices_json=final_prices(current.official_prices_json, markup_bps),
            source_type="markup_recalculation",
            source_reference=current.source_reference,
            source_hash=_source_hash({"previous": current.id, "markup_bps": markup_bps}),
            approved_at=_now(),
            approved_by_user_id=admin_user_id,
        )
        db.add(replacement)
        db.flush()
        model.active_pricing_id = replacement.id
    db.commit()
    db.refresh(policy)
    return policy
