from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from ipaddress import ip_address
from typing import Any, Generator

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_current_user, get_db, require_admin
from packages.database.models import (
    GatewayApiKey,
    GatewayIPBlock,
    GatewayModel,
    GatewayPriceRevision,
    GatewayProvider,
    GatewayProviderSync,
    GatewayRequestLog,
    User,
)
from packages.gateway.contracts import GatewayProviderError, GatewayUsage
from packages.gateway.metadata import (
    approve_price_revision,
    bootstrap_gateway_catalog,
    health_check_providers,
    pricing_policy,
    set_default_markup,
    sync_all_provider_metadata,
    sync_provider_metadata,
)
from packages.gateway.registry import provider_registry
from packages.gateway.security import (
    authenticate_api_key,
    client_ip,
    create_api_key,
    list_api_keys,
    rotate_api_key,
    serialize_api_key,
    set_api_key_status,
)
from packages.gateway.service import (
    assert_gateway_account_available,
    elapsed_ms,
    execute_chat,
    gateway_account,
    model_list,
    record_request,
    stream_chat,
)


router = APIRouter(prefix="/gateway", tags=["gateway"])
openai_router = APIRouter(prefix="/v1", tags=["OpenAI compatible gateway"])
admin_router = APIRouter(prefix="/admin/gateway", tags=["admin gateway"])


class CreateKeyRequest(BaseModel):
    name: str = Field(default="Default key", min_length=1, max_length=80)
    rate_limit_rpm: int | None = Field(default=None, ge=1, le=10_000)


class MarkupRequest(BaseModel):
    # Basis points: 3000 is the required default 30% markup.
    markup_bps: int = Field(ge=0, le=100_000)


class IPBlockRequest(BaseModel):
    ip_address: str = Field(min_length=3, max_length=64)
    reason: str = Field(min_length=3, max_length=300)
    expires_at: datetime | None = None


class ProviderEnableRequest(BaseModel):
    enabled: bool


class ChatCompletionsRequest(BaseModel):
    """OpenAI-compatible subset with forward-compatible request fields."""

    model_config = ConfigDict(extra="allow")

    model: str = Field(min_length=1, max_length=160)
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=500)
    stream: bool = False
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1, le=131_072)
    max_completion_tokens: int | None = Field(default=None, ge=1, le=131_072)
    response_format: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = Field(default=None, max_length=128)
    tool_choice: str | dict[str, Any] | None = None
    functions: list[dict[str, Any]] | None = Field(default=None, max_length=128)
    function_call: str | dict[str, Any] | None = None
    stream_options: dict[str, Any] | None = None

    def provider_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True, exclude={"model", "stream"})


def _admin(user: User = Depends(get_current_user)) -> User:
    require_admin(user)
    return user


def _gateway_enabled() -> None:
    if not get_settings().gateway_enabled:
        raise HTTPException(status_code=404, detail={"code": "GATEWAY_DISABLED"})


def _gateway_key(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> GatewayApiKey:
    _gateway_enabled()
    scheme, _, raw_key = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not raw_key:
        raise HTTPException(status_code=401, detail={"code": "GATEWAY_INVALID_API_KEY"})
    return authenticate_api_key(db, raw_key, request)


def _openai_error(exc: GatewayProviderError, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": str(exc),
                "type": "gateway_error",
                "param": None,
                "code": exc.code,
            }
        },
        headers={"X-Request-ID": request_id},
    )


def _serialize_price(row: GatewayPriceRevision) -> dict[str, Any]:
    return {
        "id": row.id,
        "model_id": row.model_id,
        "status": row.status,
        "currency": row.currency,
        "markup_bps": row.markup_bps,
        "official_prices": row.official_prices_json,
        "final_prices": row.final_prices_json,
        "source_type": row.source_type,
        "source_reference": row.source_reference,
        "synced_at": row.synced_at.isoformat(),
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
    }


def _serialize_sync(row: GatewayProviderSync) -> dict[str, Any]:
    return {
        "id": row.id,
        "provider_id": row.provider_id,
        "status": row.status,
        "triggered_by": row.triggered_by,
        "models_seen": row.models_seen,
        "prices_seen": row.prices_seen,
        "summary": row.summary_json or {},
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def _serialize_request(row: GatewayRequestLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "request_id": row.request_id,
        "model": row.public_model,
        "status": row.status,
        "http_status": row.http_status,
        "latency_ms": row.latency_ms,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "cache_tokens": row.cache_tokens,
        "reasoning_tokens": row.reasoning_tokens,
        "long_context_tokens": row.long_context_tokens,
        "image_units": row.image_units,
        "audio_units": row.audio_units,
        "search_units": row.search_units,
        "upload_units": row.upload_units,
        "download_units": row.download_units,
        "batch_units": row.batch_units,
        "cost_usd": str(row.retail_cost_usd),
        "provider_cost_usd": str(row.provider_cost_usd),
        "error_code": row.error_code,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/keys")
def keys(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"keys": [serialize_api_key(row) for row in list_api_keys(db, user.id)], "limit": 10}


@router.post("/keys", status_code=201)
def create_key(payload: CreateKeyRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    row, raw_key = create_api_key(db, user, name=payload.name, rate_limit_rpm=payload.rate_limit_rpm)
    return {"key": raw_key, "api_key": serialize_api_key(row)}


@router.post("/keys/{key_id}/pause")
def pause_key(key_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        return {"api_key": serialize_api_key(set_api_key_status(db, user.id, key_id, "paused"))}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc)}) from exc


@router.post("/keys/{key_id}/resume")
def resume_key(key_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        return {"api_key": serialize_api_key(set_api_key_status(db, user.id, key_id, "active"))}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc)}) from exc


@router.delete("/keys/{key_id}")
def revoke_key(key_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, bool]:
    try:
        set_api_key_status(db, user.id, key_id, "revoked")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc)}) from exc
    return {"ok": True}


@router.post("/keys/{key_id}/rotate")
def rotate_key(key_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        row, raw_key = rotate_api_key(db, user, key_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc)}) from exc
    return {"key": raw_key, "api_key": serialize_api_key(row)}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    account = gateway_account(db, user.id)
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    base = db.query(GatewayRequestLog).filter_by(user_id=user.id, status="success")
    total = base.with_entities(func.coalesce(func.sum(GatewayRequestLog.retail_cost_usd), 0)).scalar()
    today = base.filter(GatewayRequestLog.created_at >= day_start).with_entities(func.coalesce(func.sum(GatewayRequestLog.retail_cost_usd), 0)).scalar()
    month = base.filter(GatewayRequestLog.created_at >= month_start).with_entities(func.coalesce(func.sum(GatewayRequestLog.retail_cost_usd), 0)).scalar()
    models = (
        base.with_entities(
            GatewayRequestLog.public_model.label("model"),
            func.count(GatewayRequestLog.id).label("requests"),
            func.coalesce(func.sum(GatewayRequestLog.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(GatewayRequestLog.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(GatewayRequestLog.retail_cost_usd), 0).label("cost_usd"),
        )
        .group_by(GatewayRequestLog.public_model)
        .order_by(func.sum(GatewayRequestLog.retail_cost_usd).desc())
        .all()
    )
    return {
        "account": {
            "status": account.status,
            "monthly_spend_limit_usd": str(account.monthly_spend_limit_usd),
            "current_month_spend_usd": str(account.current_month_spend_usd),
            "month_started_at": account.current_month_started_at.isoformat(),
        },
        "subscription": {"plan": user.plan, "stripe_customer_id": user.stripe_customer_id},
        "spend_usd": {"today": str(today), "month": str(month), "lifetime": str(total)},
        "models": [
            {
                "model": row.model,
                "requests": row.requests,
                "input_tokens": row.input_tokens,
                "output_tokens": row.output_tokens,
                "cost_usd": str(row.cost_usd),
            }
            for row in models
        ],
    }


@router.get("/requests")
def request_history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    query = db.query(GatewayRequestLog).filter_by(user_id=user.id)
    total = query.count()
    rows = query.order_by(GatewayRequestLog.created_at.desc()).offset(offset).limit(limit).all()
    return {"requests": [_serialize_request(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@openai_router.get("/models")
def openai_models(_: GatewayApiKey = Depends(_gateway_key), db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"object": "list", "data": model_list(db)}


@openai_router.post("/chat/completions")
def chat_completions(
    payload: ChatCompletionsRequest,
    request: Request,
    api_key: GatewayApiKey = Depends(_gateway_key),
    db: Session = Depends(get_db),
):
    request_id = request.headers.get("x-request-id", "")[:128] or f"chatcmpl_{uuid.uuid4().hex}"
    started = time.perf_counter()
    route = None
    try:
        assert_gateway_account_available(db, api_key.user_id)
        if payload.stream:
            execution = stream_chat(db, payload.model, payload.provider_payload())
            route = execution.route
            return _streaming_response(execution, payload.model, request_id, api_key, client_ip(request), db, started)
        result, route = execute_chat(db, payload.model, payload.provider_payload())
        record_request(
            db,
            request_id=request_id,
            api_key=api_key,
            route=route,
            public_model=payload.model,
            usage=result.usage,
            status="success",
            http_status=200,
            latency_ms=elapsed_ms(started),
            ip_address=client_ip(request),
        )
        message: dict[str, Any] = {"role": "assistant", "content": result.content}
        if result.tool_calls:
            message["tool_calls"] = result.tool_calls
        if result.function_call:
            message["function_call"] = result.function_call
        return JSONResponse(
            content={
                "id": request_id,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": payload.model,
                "choices": [{"index": 0, "message": message, "finish_reason": result.finish_reason or "stop"}],
                "usage": {
                    "prompt_tokens": result.usage.input_tokens,
                    "completion_tokens": result.usage.output_tokens,
                    "total_tokens": result.usage.input_tokens + result.usage.output_tokens,
                    "prompt_tokens_details": {"cached_tokens": result.usage.cache_tokens},
                    "completion_tokens_details": {"reasoning_tokens": result.usage.reasoning_tokens},
                },
            },
            headers={"X-Request-ID": request_id},
        )
    except GatewayProviderError as exc:
        try:
            record_request(
                db,
                request_id=request_id,
                api_key=api_key,
                route=route,
                public_model=payload.model,
                usage=None,
                status="error",
                http_status=exc.status_code,
                latency_ms=elapsed_ms(started),
                ip_address=client_ip(request),
                error_code=exc.code,
            )
        except Exception:
            db.rollback()
        return _openai_error(exc, request_id)


def _streaming_response(execution, public_model: str, request_id: str, api_key: GatewayApiKey, ip_address: str, db: Session, started: float) -> StreamingResponse:
    created = int(time.time())

    def event_stream() -> Generator[str, None, None]:
        usage = GatewayUsage()
        terminal_logged = False
        try:
            for event in execution.events:
                if event.usage:
                    usage = event.usage
                if event.done:
                    record_request(
                        db,
                        request_id=request_id,
                        api_key=api_key,
                        route=execution.route,
                        public_model=public_model,
                        usage=usage,
                        status="success",
                        http_status=200,
                        latency_ms=elapsed_ms(started),
                        ip_address=ip_address,
                    )
                    terminal_logged = True
                    yield "data: [DONE]\n\n"
                    return
                body: dict[str, Any] = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": public_model,
                    "choices": [],
                }
                if event.delta or event.finish_reason is not None:
                    body["choices"] = [{"index": 0, "delta": event.delta, "finish_reason": event.finish_reason}]
                if event.usage:
                    body["usage"] = {
                        "prompt_tokens": event.usage.input_tokens,
                        "completion_tokens": event.usage.output_tokens,
                        "total_tokens": event.usage.input_tokens + event.usage.output_tokens,
                    }
                yield f"data: {json.dumps(body, separators=(',', ':'))}\n\n"
            # Some official APIs close the stream without a [DONE] marker.
            record_request(
                db,
                request_id=request_id,
                api_key=api_key,
                route=execution.route,
                public_model=public_model,
                usage=usage,
                status="success",
                http_status=200,
                latency_ms=elapsed_ms(started),
                ip_address=ip_address,
            )
            terminal_logged = True
            yield "data: [DONE]\n\n"
        except GatewayProviderError as exc:
            if not terminal_logged:
                try:
                    record_request(
                        db,
                        request_id=request_id,
                        api_key=api_key,
                        route=execution.route,
                        public_model=public_model,
                        usage=usage,
                        status="error",
                        http_status=exc.status_code,
                        latency_ms=elapsed_ms(started),
                        ip_address=ip_address,
                        error_code=exc.code,
                    )
                except Exception:
                    db.rollback()
            yield f"data: {json.dumps({'error': {'message': str(exc), 'type': 'gateway_error', 'code': exc.code}}, separators=(',', ':'))}\n\n"
        except Exception:
            db.rollback()
            yield "data: {\"error\":{\"message\":\"Gateway stream interrupted\",\"type\":\"gateway_error\",\"code\":\"GATEWAY_STREAM_INTERRUPTED\"}}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no", "X-Request-ID": request_id},
    )


@admin_router.post("/bootstrap")
def bootstrap(db: Session = Depends(get_db), _: User = Depends(_admin)) -> dict[str, int]:
    return bootstrap_gateway_catalog(db)


@admin_router.get("/providers")
def providers(db: Session = Depends(get_db), _: User = Depends(_admin)) -> dict[str, Any]:
    rows = db.query(GatewayProvider).order_by(GatewayProvider.name).all()
    return {
        "providers": [
            {
                "id": row.id,
                "name": row.name,
                "display_name": row.display_name,
                "enabled": row.enabled,
                "health_status": row.health_status,
                "last_health_at": row.last_health_at.isoformat() if row.last_health_at else None,
                "last_error": row.last_error,
                "models": db.query(GatewayModel).filter_by(provider_id=row.id).count(),
            }
            for row in rows
        ],
        "registered_plugins": provider_registry.names(),
    }


@admin_router.put("/providers/{provider_name}")
def enable_provider(provider_name: str, payload: ProviderEnableRequest, db: Session = Depends(get_db), _: User = Depends(_admin)) -> dict[str, Any]:
    if provider_name not in provider_registry.names():
        raise HTTPException(status_code=400, detail={"code": "GATEWAY_PROVIDER_PLUGIN_REQUIRED"})
    bootstrap_gateway_catalog(db)
    row = db.query(GatewayProvider).filter_by(name=provider_name).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail={"code": "GATEWAY_PROVIDER_NOT_FOUND"})
    row.enabled = payload.enabled
    db.commit()
    return {"id": row.id, "name": row.name, "enabled": row.enabled}


@admin_router.post("/providers/healthcheck")
def healthcheck(db: Session = Depends(get_db), _: User = Depends(_admin)) -> dict[str, Any]:
    return {"providers": health_check_providers(db)}


@admin_router.post("/providers/{provider_name}/sync")
def sync_one(provider_name: str, db: Session = Depends(get_db), user: User = Depends(_admin)) -> dict[str, Any]:
    try:
        return {"sync": _serialize_sync(sync_provider_metadata(db, provider_name, triggered_by="admin", triggered_by_user_id=user.id))}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc)}) from exc


@admin_router.post("/sync")
def sync_all(db: Session = Depends(get_db), _: User = Depends(_admin)) -> dict[str, Any]:
    return {"syncs": [_serialize_sync(row) for row in sync_all_provider_metadata(db, triggered_by="admin")]}


@admin_router.get("/syncs")
def syncs(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db), _: User = Depends(_admin)) -> dict[str, Any]:
    rows = db.query(GatewayProviderSync).order_by(GatewayProviderSync.created_at.desc()).limit(limit).all()
    return {"syncs": [_serialize_sync(row) for row in rows]}


@admin_router.get("/prices/pending")
def pending_prices(db: Session = Depends(get_db), _: User = Depends(_admin)) -> dict[str, Any]:
    rows = db.query(GatewayPriceRevision).filter_by(status="pending").order_by(GatewayPriceRevision.synced_at.desc()).all()
    return {"revisions": [_serialize_price(row) for row in rows]}


@admin_router.get("/pricing/policy")
def current_pricing_policy(db: Session = Depends(get_db), _: User = Depends(_admin)) -> dict[str, Any]:
    policy = pricing_policy(db)
    db.commit()
    return {"policy": {"id": policy.id, "markup_bps": policy.markup_bps, "updated_at": policy.updated_at.isoformat()}}


@admin_router.post("/prices/{revision_id}/approve")
def approve_price(revision_id: str, db: Session = Depends(get_db), user: User = Depends(_admin)) -> dict[str, Any]:
    try:
        return {"revision": _serialize_price(approve_price_revision(db, revision_id, user.id))}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc)}) from exc


@admin_router.put("/pricing/markup")
def update_markup(payload: MarkupRequest, db: Session = Depends(get_db), user: User = Depends(_admin)) -> dict[str, Any]:
    policy = set_default_markup(db, payload.markup_bps, user.id)
    return {"policy": {"id": policy.id, "markup_bps": policy.markup_bps, "updated_at": policy.updated_at.isoformat()}}


@admin_router.get("/metrics")
def metrics(db: Session = Depends(get_db), _: User = Depends(_admin)) -> dict[str, Any]:
    revenue = db.query(func.coalesce(func.sum(GatewayRequestLog.retail_cost_usd), 0)).filter_by(status="success").scalar()
    cost = db.query(func.coalesce(func.sum(GatewayRequestLog.provider_cost_usd), 0)).filter_by(status="success").scalar()
    requests = db.query(func.count(GatewayRequestLog.id)).scalar()
    return {"revenue_usd": str(revenue), "provider_cost_usd": str(cost), "profit_usd": str(Decimal(str(revenue)) - Decimal(str(cost))), "requests": requests}


@admin_router.post("/ip-blocks", status_code=201)
def add_ip_block(payload: IPBlockRequest, db: Session = Depends(get_db), user: User = Depends(_admin)) -> dict[str, Any]:
    normalized_ip = payload.ip_address.strip()
    try:
        normalized_ip = str(ip_address(normalized_ip))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "GATEWAY_IP_INVALID"}) from exc
    row = db.query(GatewayIPBlock).filter_by(ip_address=normalized_ip).one_or_none()
    if row is None:
        row = GatewayIPBlock(ip_address=normalized_ip, reason=payload.reason, expires_at=payload.expires_at, created_by_user_id=user.id)
        db.add(row)
    else:
        row.active = True
        row.reason = payload.reason
        row.expires_at = payload.expires_at
        row.created_by_user_id = user.id
    db.commit()
    return {"id": row.id, "ip_address": row.ip_address, "active": row.active}


@admin_router.delete("/ip-blocks/{block_id}")
def remove_ip_block(block_id: str, db: Session = Depends(get_db), _: User = Depends(_admin)) -> dict[str, bool]:
    row = db.get(GatewayIPBlock, block_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "GATEWAY_IP_BLOCK_NOT_FOUND"})
    row.active = False
    db.commit()
    return {"ok": True}
