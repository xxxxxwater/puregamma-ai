"""TypeSafe Jev's native typed-evaluation API; deliberately NOT chat completions."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db
from apps.api.routers.gateway import _gateway_key, _gateway_enabled
from packages.database.models import GatewayApiKey
from packages.gateway.contracts import GatewayProviderError
from packages.gateway.providers.typesafe import TypeSafeJevProvider
from packages.gateway.security import client_ip
from packages.gateway.service import _route_for_model, assert_gateway_account_available, elapsed_ms, model_list, record_request


router = APIRouter(prefix="/v1", tags=["System One gateway"])


class SystemOneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1, max_length=160)
    state: str | dict[str, Any] | list[Any]
    questions: dict[str, dict[str, Any]] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_questions(self) -> "SystemOneRequest":
        # Cap request size before any billed upstream call. This limit is a
        # PureGamma product guardrail, not a claim about TypeSafe's context size.
        if len(json.dumps(self.model_dump(), ensure_ascii=False, allow_nan=False).encode("utf-8")) > 262_144:
            raise ValueError("system one request exceeds 256 KiB")
        for question_id, question in self.questions.items():
            if not question_id or len(question_id) > 80 or not isinstance(question, dict):
                raise ValueError("invalid question id")
            kind = question.get("type")
            if kind not in {"noul", "choice", "score"} or not isinstance(question.get("instructions"), (str, list, dict)):
                raise ValueError("invalid question type or instructions")
            if kind == "choice" and (not isinstance(question.get("criteria"), dict) or len(question["criteria"]) < 2 or any(not isinstance(value, (str, type(None))) for value in question["criteria"].values())):
                raise ValueError("choice requires at least two described alternatives")
            if kind == "score" and (not isinstance(question.get("criteria"), list) or len(question["criteria"]) < 2):
                raise ValueError("score requires at least two levels")
            if kind == "noul" and "criteria" in question and (not isinstance(question["criteria"], dict) or not set(question["criteria"]).issubset({"true", "false"})):
                raise ValueError("invalid noul criteria")
        return self


@router.get("/systemone/models")
def system_one_models(_: GatewayApiKey = Depends(_gateway_key), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Expose approved native evaluation models separately from chat models."""
    return {"object": "list", "data": [row for row in model_list(db) if row["capabilities"].get("system_one") is True]}


@router.post("/systemone")
def system_one(
    payload: SystemOneRequest,
    request: Request,
    api_key: GatewayApiKey = Depends(_gateway_key),
    db: Session = Depends(get_db),
) -> JSONResponse:
    request_id = request.headers.get("x-request-id", "")[:128] or f"jev_{uuid.uuid4().hex}"
    started = time.perf_counter()
    route = None
    try:
        assert_gateway_account_available(db, api_key.user_id)
        route = _route_for_model(db, payload.model)
        if not route.model.capabilities_json.get("system_one") or not isinstance(route.adapter, TypeSafeJevProvider):
            raise GatewayProviderError("GATEWAY_CAPABILITY_UNAVAILABLE", "The model does not support System One", status_code=400, retryable=False)
        result, usage = route.adapter.evaluate(route.model.provider_model_id, state=payload.state, questions=payload.questions)
        log = record_request(
            db, request_id=request_id, api_key=api_key, route=route, public_model=payload.model,
            usage=usage, status="success", http_status=200, latency_ms=elapsed_ms(started), ip_address=client_ip(request),
        )
        return JSONResponse(
            content={**result, "request_id": request_id, "billing": {"currency": "USD", "amount_usd": str(log.retail_cost_usd)}},
            headers={"X-Request-ID": request_id},
        )
    except GatewayProviderError as exc:
        record_request(
            db, request_id=request_id, api_key=api_key, route=route, public_model=payload.model,
            usage=None, status="error", http_status=exc.status_code, latency_ms=elapsed_ms(started),
            ip_address=client_ip(request), error_code=exc.code,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": str(exc)}},
            headers={"X-Request-ID": request_id},
        )
