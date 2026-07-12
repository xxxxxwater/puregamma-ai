from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from apps.api.config import get_settings
from apps.api.dependencies import ensure_bootstrap
from apps.api.routers import admin, agent, assets, auth, backtest, billing, google_auth, market, notifications, options, playbooks, portfolio, reports, signals, strategies, stripe_webhook, trading


settings = get_settings()
app = FastAPI(title="PureGamma AI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    ensure_bootstrap()


@app.get("/health")
def health() -> dict:
    from packages.agents.llm.provider_factory import llm_status
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
    llm = llm_status(settings)
    return {
        "status": "ok" if database_status == "ok" else "degraded",
        "service": "puregamma-api",
        "database": database_status,
        "redis": "not_checked",
        "stripe_configured": bool(settings.stripe_secret_key),
        "stripe_webhook_secret_configured": bool(settings.stripe_webhook_secret),
        "billing_mode": settings.billing_mode,
        "billing_checkout_mode": settings.billing_checkout_mode,
        "google_oauth_configured": bool(settings.google_client_id and settings.google_client_secret),
        "stripe_webhook_tolerance_seconds": settings.stripe_webhook_tolerance_seconds,
        "deepseek_configured": bool(settings.deepseek_api_key),
        "llm_provider": llm["provider"],
        "llm_model": llm["model"],
        "imessage_status": settings.imessage_provider,
        "mock_mode": settings.billing_mode == "mock" or llm["active_provider"] == "mock",
    }


app.include_router(auth.router)
app.include_router(google_auth.router)
app.include_router(assets.router)
app.include_router(market.router)
app.include_router(options.router)
app.include_router(reports.router)
app.include_router(signals.router)
app.include_router(playbooks.router)
app.include_router(backtest.router)
app.include_router(strategies.router)
app.include_router(trading.router)
app.include_router(portfolio.router)
app.include_router(billing.router)
app.include_router(stripe_webhook.router)
app.include_router(notifications.router)
app.include_router(admin.router)
app.include_router(agent.router)
app.include_router(agent.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
