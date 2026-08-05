from __future__ import annotations

import hmac
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.config import get_settings
from app.runtime_manager import RuntimeManager


settings = get_settings()
manager = RuntimeManager(settings.state_db)
app = FastAPI(title="PureGamma Nautilus Runtime", version="0.1.0")


class RuntimeCommand(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=200)
    payload: dict[str, Any]


def internal_auth(x_pg_runtime_secret: str | None = Header(default=None)) -> None:
    if not x_pg_runtime_secret or not hmac.compare_digest(
        x_pg_runtime_secret, settings.runtime_secret
    ):
        raise HTTPException(status_code=401, detail="Invalid runtime credential")


@app.middleware("http")
async def limit_body(request: Request, call_next):
    length = int(request.headers.get("content-length", "0") or 0)
    if length > settings.max_message_bytes:
        raise HTTPException(status_code=413, detail="Runtime command is too large")
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    return manager.health()


@app.get("/runs", dependencies=[Depends(internal_auth)])
def runs() -> dict:
    return {"runs": manager.store.list_runs()}


@app.get("/runs/{run_id}", dependencies=[Depends(internal_auth)])
def run(run_id: str) -> dict:
    value = manager.store.get_run(run_id)
    if not value:
        raise HTTPException(status_code=404, detail="Runtime run not found")
    return {"run": value}


@app.get("/market/quotes", dependencies=[Depends(internal_auth)])
def market_quotes(
    symbols: list[str] = Query(default=[]), refresh: bool = Query(default=False)
) -> dict:
    if refresh:
        return manager.refresh_market_data(symbols, force=True)
    return {
        "status": "CACHED",
        "quotes": manager.store.list_market_quotes(),
        "providers": manager.market_data.status(),
        "liveOrders": False,
    }


@app.get("/events", dependencies=[Depends(internal_auth)])
def events(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    return {"events": manager.store.list_events(limit=limit)}


@app.get("/accounts/{account_id}/state", dependencies=[Depends(internal_auth)])
def account_state(account_id: str) -> dict:
    return manager.account_state(account_id)


@app.post("/commands/{command_type}", dependencies=[Depends(internal_auth)])
def command(command_type: str, request: RuntimeCommand) -> dict:
    if request.payload.get("mode", "").upper() == "LIVE":
        raise HTTPException(status_code=403, detail="LIVE execution is disabled")
    return manager.command(command_type, request.idempotency_key, request.payload)
