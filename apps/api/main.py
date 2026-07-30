from __future__ import annotations

import os
import time
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from apps.api.config import get_settings, validate_production_settings
from apps.api.dependencies import ensure_bootstrap
from apps.api.routers import admin, agent, apple_auth, assets, auth, backtest, backtest_lab, billing, captcha, email_auth, gateway, google_auth, hyperliquid_stream, imessage_agent, mobile_auth, internal, market, notifications, options, playbooks, portfolio, reports, secretary, signals, skills, strategies, stripe_webhook, trading


settings = get_settings()
validate_production_settings(settings)
logger = logging.getLogger("puregamma.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_bootstrap()
    yield


# API schema/docs are a developer surface; keep them off in production unless
# explicitly re-enabled for an internal environment.
_docs_enabled = (
    settings.app_environment.lower() != "production"
    or os.getenv("API_DOCS_ENABLED", "").lower() == "true"
)

app = FastAPI(
    title="PureGamma AI API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)
_expensive_paths = ("/agent/", "/secretary/", "/reports/", "/backtest", "/market/intelligence", "/options/")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def cookie_csrf_guard(request: Request, call_next):
    """Require an approved Origin for browser state changes using the session cookie."""
    if (
        settings.app_environment.lower() == "production"
        and request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
        and request.cookies.get(settings.session_cookie_name)
        and not request.headers.get("authorization")
        and request.url.path != "/stripe/webhook"
    ):
        origin = request.headers.get("origin", "").rstrip("/")
        if origin not in settings.cors_origins:
            return JSONResponse(
                status_code=403,
                content={"detail": {"code": "CSRF_ORIGIN_REJECTED"}},
            )
    return await call_next(request)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if settings.app_environment.lower() != "production" or request.url.path in {"/health", "/stripe/webhook"}:
        return await call_next(request)
    forwarded = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for")
    client = forwarded.split(",", 1)[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    expensive = any(part in request.url.path for part in _expensive_paths)
    limit = settings.expensive_rate_limit_per_minute if expensive else settings.api_rate_limit_per_minute
    minute = int(time.time() // 60)
    bucket_key = f"pg:rate:{'expensive' if expensive else 'general'}:{client}:{minute}"
    try:
        from apps.api.redis_client import get_redis

        pipeline = get_redis().pipeline(transaction=True)
        pipeline.incr(bucket_key)
        pipeline.expire(bucket_key, 120)
        count, _ = pipeline.execute()
    except Exception:
        logger.exception("rate_limit_backend_unavailable")
        return JSONResponse(
            status_code=503,
            content={"detail": "Rate limit service unavailable"},
            headers={"Retry-After": "10"},
        )
    if int(count) > limit:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": "60"},
        )
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
    """Process liveness only; dependency readiness is exposed separately."""
    return {"status": "ok", "service": "puregamma-api"}


@app.get("/ready")
def readiness():
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
        from apps.api.redis_client import get_redis

        get_redis().ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"
    ready = database_status == "ok" and (
        redis_status == "ok" or settings.app_environment.lower() != "production"
    )
    payload = {
        "status": "ok" if ready else "degraded",
        "service": "puregamma-api",
        "database": database_status,
        "redis": redis_status,
    }
    return JSONResponse(status_code=200 if ready else 503, content=payload)


app.include_router(auth.router)
app.include_router(email_auth.router)
app.include_router(captcha.router)
app.include_router(google_auth.router)
app.include_router(mobile_auth.router)
app.include_router(apple_auth.router)
app.include_router(assets.router)
app.include_router(market.router)
app.include_router(hyperliquid_stream.router)
app.include_router(options.router)
app.include_router(reports.router)
app.include_router(backtest.router)
app.include_router(backtest_lab.router)
app.include_router(gateway.router)
app.include_router(gateway.openai_router)
app.include_router(gateway.admin_router)
app.include_router(portfolio.router)
app.include_router(billing.router)
app.include_router(internal.router)
app.include_router(imessage_agent.router)
app.include_router(stripe_webhook.router)
app.include_router(notifications.router)
app.include_router(agent.router, prefix="/api")
app.include_router(secretary.router, prefix="/api")
app.include_router(skills.router, prefix="/api")
app.include_router(admin.router)
if not settings.initial_launch_mode:
    app.include_router(signals.router)
    app.include_router(playbooks.router)
    app.include_router(strategies.router)
    app.include_router(trading.router)
