from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterator

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import (
    GatewayAccount,
    GatewayApiKey,
    GatewayModel,
    GatewayPriceRevision,
    GatewayProvider as GatewayProviderRecord,
    GatewayRequestLog,
)
from packages.gateway.contracts import GatewayChatResult, GatewayProvider as GatewayProviderAdapter, GatewayProviderError, GatewayStreamEvent, GatewayUsage
from packages.gateway.pricing import usage_cost
from packages.gateway.registry import provider_registry


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _month_start(value: datetime | None = None) -> datetime:
    current = value or _now()
    return current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@dataclass(frozen=True)
class GatewayRoute:
    model: GatewayModel
    provider: GatewayProviderRecord
    pricing: GatewayPriceRevision
    adapter: GatewayProviderAdapter


@dataclass
class GatewayStreamExecution:
    route: GatewayRoute
    events: Iterator[GatewayStreamEvent]


def _route_for_model(db: Session, public_model: str, *, allow_unhealthy: bool = False) -> GatewayRoute:
    model = db.query(GatewayModel).filter_by(public_id=public_model, status="active").one_or_none()
    if model is None:
        raise GatewayProviderError("GATEWAY_MODEL_NOT_AVAILABLE", f"Model '{public_model}' is not available", status_code=404, retryable=False)
    provider = db.query(GatewayProviderRecord).filter_by(id=model.provider_id, enabled=True).one_or_none()
    if provider is None:
        raise GatewayProviderError("GATEWAY_PROVIDER_DISABLED", "The selected provider is unavailable", status_code=503)
    if provider.health_status == "unhealthy" and not allow_unhealthy:
        raise GatewayProviderError("GATEWAY_PROVIDER_UNHEALTHY", "The selected provider is unhealthy", status_code=503)
    pricing = db.get(GatewayPriceRevision, model.active_pricing_id) if model.active_pricing_id else None
    if pricing is None or pricing.status != "active":
        # A catalog sync never turns pricing live on its own. This protects
        # customers from being charged against an unreviewed provider update.
        raise GatewayProviderError("GATEWAY_PRICING_NOT_APPROVED", "Model pricing is awaiting administrator approval", status_code=503, retryable=False)
    adapter = provider_registry.create(provider.name, get_settings(), dict(provider.metadata_json or {}))
    return GatewayRoute(model=model, provider=provider, pricing=pricing, adapter=adapter)


def resolve_routes(db: Session, public_model: str) -> list[GatewayRoute]:
    """Resolve database-configured primary plus optional same-API failovers.

    `routing.failover_models` is a list of public model ids. No provider names
    are special-cased: adding a Provider plugin or a database model is enough.
    """
    primary = _route_for_model(db, public_model, allow_unhealthy=True)
    configured = (primary.model.routing_json or {}).get("failover_models") or []
    candidates = [public_model, *[str(item) for item in configured]]
    routes: list[GatewayRoute] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            route = _route_for_model(db, candidate)
        except GatewayProviderError:
            continue
        routes.append(route)
    if routes:
        return routes
    if primary.provider.health_status == "unhealthy":
        raise GatewayProviderError("GATEWAY_PROVIDER_UNHEALTHY", "The selected provider is unhealthy", status_code=503)
    # Preserve the exact, useful primary error when all configured choices are
    # unavailable, including the case where the primary is only temporarily
    # unhealthy and no failover was configured.
    return [primary]


def _record_provider_success(db: Session, provider: GatewayProviderRecord) -> None:
    provider.health_status = "healthy"
    provider.last_health_at = _now()
    provider.last_error = None
    provider.consecutive_failures = 0


def _record_provider_failure(db: Session, provider: GatewayProviderRecord, exc: GatewayProviderError) -> None:
    provider.last_health_at = _now()
    provider.last_error = exc.code[:500]
    provider.consecutive_failures = int(provider.consecutive_failures or 0) + 1
    if provider.consecutive_failures >= 3:
        provider.health_status = "unhealthy"


def execute_chat(db: Session, public_model: str, request: dict[str, Any]) -> tuple[GatewayChatResult, GatewayRoute]:
    last_error: GatewayProviderError | None = None
    for route in resolve_routes(db, public_model):
        try:
            result = route.adapter.chat(route.model.provider_model_id, request)
            _record_provider_success(db, route.provider)
            return result, route
        except GatewayProviderError as exc:
            _record_provider_failure(db, route.provider, exc)
            last_error = exc
            if not exc.retryable:
                break
    if last_error:
        raise last_error
    raise GatewayProviderError("GATEWAY_ROUTE_UNAVAILABLE", "No route is available", status_code=503)


def stream_chat(db: Session, public_model: str, request: dict[str, Any]) -> GatewayStreamExecution:
    """Return a stream from the chosen route.

    Failover is safe only before a provider emits bytes. The generator below
    will attempt configured fallbacks for connection/setup errors, but after a
    chunk is sent it surfaces the error rather than changing providers mid-turn.
    """
    routes = resolve_routes(db, public_model)
    first = routes[0]
    execution: GatewayStreamExecution

    def iterator() -> Iterator[GatewayStreamEvent]:
        last_error: GatewayProviderError | None = None
        for route in routes:
            emitted = False
            try:
                execution.route = route
                for event in route.adapter.stream(route.model.provider_model_id, request):
                    emitted = True
                    yield event
                _record_provider_success(db, route.provider)
                return
            except GatewayProviderError as exc:
                _record_provider_failure(db, route.provider, exc)
                last_error = exc
                if emitted or not exc.retryable:
                    raise
        if last_error:
            raise last_error
        raise GatewayProviderError("GATEWAY_ROUTE_UNAVAILABLE", "No route is available", status_code=503)

    execution = GatewayStreamExecution(route=first, events=iterator())
    return execution


def gateway_account(db: Session, user_id: str) -> GatewayAccount:
    account = db.query(GatewayAccount).filter_by(user_id=user_id).one_or_none()
    if account is None:
        account = GatewayAccount(user_id=user_id, current_month_started_at=_month_start())
        db.add(account)
        db.flush()
    if account.current_month_started_at < _month_start():
        account.current_month_started_at = _month_start()
        account.current_month_spend_usd = Decimal("0")
    return account


def assert_gateway_account_available(db: Session, user_id: str) -> GatewayAccount:
    account = gateway_account(db, user_id)
    if account.status != "active":
        raise GatewayProviderError("GATEWAY_ACCOUNT_INACTIVE", "Gateway account is inactive", status_code=403, retryable=False)
    limit = Decimal(str(account.monthly_spend_limit_usd or 0))
    spent = Decimal(str(account.current_month_spend_usd or 0))
    if limit > 0 and spent >= limit:
        raise GatewayProviderError("GATEWAY_MONTHLY_LIMIT_REACHED", "Monthly gateway spend limit reached", status_code=402, retryable=False)
    return account


def record_request(
    db: Session,
    *,
    request_id: str,
    api_key: GatewayApiKey,
    route: GatewayRoute | None,
    public_model: str,
    usage: GatewayUsage | None,
    status: str,
    http_status: int,
    latency_ms: int,
    ip_address: str,
    error_code: str | None = None,
) -> GatewayRequestLog:
    measured = usage or GatewayUsage()
    official_cost = usage_cost(route.pricing.official_prices_json, measured) if route else Decimal("0")
    retail_cost = usage_cost(route.pricing.final_prices_json, measured) if route else Decimal("0")
    row = GatewayRequestLog(
        request_id=request_id,
        user_id=api_key.user_id,
        api_key_id=api_key.id,
        provider_id=route.provider.id if route else None,
        model_id=route.model.id if route else None,
        public_model=public_model,
        status=status,
        http_status=http_status,
        latency_ms=max(0, latency_ms),
        input_tokens=measured.input_tokens,
        output_tokens=measured.output_tokens,
        cache_tokens=measured.cache_tokens,
        reasoning_tokens=measured.reasoning_tokens,
        long_context_tokens=measured.long_context_tokens,
        image_units=measured.image_units,
        audio_units=measured.audio_units,
        search_units=measured.search_units,
        upload_units=measured.upload_units,
        download_units=measured.download_units,
        batch_units=measured.batch_units,
        provider_cost_usd=official_cost,
        retail_cost_usd=retail_cost,
        ip_address=ip_address,
        error_code=error_code,
    )
    db.add(row)
    if status == "success":
        account = gateway_account(db, api_key.user_id)
        account.current_month_spend_usd = Decimal(str(account.current_month_spend_usd or 0)) + retail_cost
    db.commit()
    return row


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def serialize_model(model: GatewayModel, provider: GatewayProviderRecord) -> dict[str, Any]:
    return {
        "id": model.public_id,
        "object": "model",
        "created": int(model.created_at.timestamp()) if model.created_at else 0,
        "owned_by": provider.name,
        "display_name": model.display_name,
        "capabilities": model.capabilities_json or {},
    }


def model_list(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(GatewayModel, GatewayProviderRecord)
        .join(GatewayProviderRecord, GatewayModel.provider_id == GatewayProviderRecord.id)
        .filter(GatewayModel.status == "active", GatewayProviderRecord.enabled.is_(True))
        .order_by(GatewayModel.public_id)
        .all()
    )
    return [serialize_model(model, provider) for model, provider in rows if model.active_pricing_id]
