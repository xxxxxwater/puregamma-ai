from __future__ import annotations

import threading
import time
import logging
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from apps.api.config import get_settings, validate_production_settings
from apps.api.dependencies import ensure_bootstrap
from apps.api.routers import admin, agent, assets, auth, backtest, billing, google_auth, market, notifications, options, playbooks, portfolio, reports, signals, strategies, stripe_webhook, trading


settings = get_settings()
validate_production_settings(settings)
logger = logging.getLogger("puregamma.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_bootstrap()
    yield


app = FastAPI(title="PureGamma AI API", version="0.1.0", lifespan=lifespan)
_rate_windows: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = threading.Lock()
_expensive_paths = ("/agent/", "/reports/", "/backtest", "/market/intelligence", "/options/")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if settings.app_environment.lower() != "production" or request.url.path in {"/health", "/stripe/webhook"}:
        return await call_next(request)
    forwarded = request.headers.get("x-forwarded-for")
    client = forwarded.split(",", 1)[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    expensive = any(part in request.url.path for part in _expensive_paths)
    limit = settings.expensive_rate_limit_per_minute if expensive else settings.api_rate_limit_per_minute
    bucket_key = f"{client}:{'expensive' if expensive else 'general'}"
    now = time.monotonic()
    with _rate_lock:
        window = _rate_windows[bucket_key]
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": "60"},
            )
        window.append(now)
    return await call_next(request)


@app.middleware("http")
async def request_trace(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "")[:128] or str(uuid.uuid4())
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed", extra={"request_id": request_id, "method": request.method, "path": request.url.path})
        raise
    response.headers["X-Request-ID"] = request_id
    logger.info("request_completed", extra={"request_id": request_id, "method": request.method, "path": request.url.path, "status_code": response.status_code, "duration_ms": int((time.perf_counter() - started) * 1000)})
    return response


@app.get("/health")
def health() -> dict:
    from packages.database.session import SessionLocal

    database_status = "unknown"
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception:
        database_status = "error"
    finally:
        db.close()
    redis_status = "unknown"
    try:
        from redis import Redis
        Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1).ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"
    return {
        "status": "ok" if database_status == "ok" and (redis_status == "ok" or settings.app_environment.lower() != "production") else "degraded",
        "service": "puregamma-api",
        "database": database_status,
        "redis": redis_status,
    }


app.include_router(auth.router)
app.include_router(google_auth.router)
app.include_router(assets.router)
app.include_router(market.router)
app.include_router(options.router)
app.include_router(reports.router)
app.include_router(backtest.router)
app.include_router(portfolio.router)
app.include_router(billing.router)
app.include_router(stripe_webhook.router)
app.include_router(notifications.router)
app.include_router(agent.router, prefix="/api")
if not settings.initial_launch_mode:
    app.include_router(signals.router)
    app.include_router(playbooks.router)
    app.include_router(strategies.router)
    app.include_router(trading.router)
    app.include_router(admin.router)
