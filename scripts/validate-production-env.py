#!/usr/bin/env python3
"""Fail-fast, redacted production environment validation."""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

REQUIRED = (
    "DATABASE_URL", "POSTGRES_PASSWORD", "REDIS_URL", "JWT_SECRET", "SESSION_SECRET",
    "ENCRYPTION_MASTER_KEY", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
    "NEXT_PUBLIC_API_URL", "SITE_URL", "APP_DOMAIN", "API_DOMAIN", "CORS_ORIGINS",
    "SESSION_COOKIE_DOMAIN", "GOOGLE_OAUTH_REDIRECT_URI", "INTERNAL_RUNTIME_SECRET",
    "NAUTILUS_RUNTIME_SECRET", "LLM_PROVIDER", "IMESSAGE_PROVIDER",
)

def main() -> int:
    if os.getenv("APP_ENV", "development").lower() not in {"production", "prod"}:
        print("APP_ENV is not production; validation skipped")
        return 0
    errors = []
    for name in REQUIRED:
        value = os.getenv(name, "")
        if not value or value.lower() in {"change-me", "dev-only-change-me", "dev-runtime-secret"}:
            errors.append(f"{name} is required")
    for name in ("JWT_SECRET", "SESSION_SECRET", "ENCRYPTION_MASTER_KEY", "INTERNAL_RUNTIME_SECRET"):
        if os.getenv(name, "") and len(os.environ[name]) < 32:
            errors.append(f"{name} must be at least 32 characters")
    if os.getenv("NAUTILUS_RUNTIME_SECRET", "") and len(os.environ["NAUTILUS_RUNTIME_SECRET"]) < 24:
        errors.append("NAUTILUS_RUNTIME_SECRET must be at least 24 characters")
    if not os.getenv("DATABASE_URL", "").startswith(("postgresql://", "postgresql+psycopg://")):
        errors.append("DATABASE_URL must use PostgreSQL")
    if os.getenv("BILLING_MODE", "stripe") != "stripe":
        errors.append("BILLING_MODE must be stripe")
    if os.getenv("AUTH_ALLOW_DEMO_FALLBACK", "false").lower() == "true":
        errors.append("AUTH_ALLOW_DEMO_FALLBACK must be false")
    if any(os.getenv(name, "false").lower() == "true" for name in ("ENABLE_MOCK_AGENT", "ENABLE_MOCK_MARKET_DATA", "ENABLE_MOCK_DATA_SOURCES")):
        errors.append("mock providers must be disabled in production")
    if os.getenv("LLM_PROVIDER", "").lower() == "deepseek" and not os.getenv("DEEPSEEK_API_KEY"):
        errors.append("DEEPSEEK_API_KEY is required for LLM_PROVIDER=deepseek")
    if os.getenv("LLM_PROVIDER", "").lower() == "openai" and (not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_MODEL")):
        errors.append("OPENAI_API_KEY and OPENAI_MODEL are required for LLM_PROVIDER=openai")
    if os.getenv("LLM_PROVIDER", "").lower() not in {"openai", "deepseek"}:
        errors.append("LLM_PROVIDER must be openai or deepseek")
    if os.getenv("IMESSAGE_PROVIDER", "").lower() not in {"disabled", "macos_relay"}:
        errors.append("IMESSAGE_PROVIDER must be disabled or macos_relay")
    for name in ("NEXT_PUBLIC_API_URL", "SITE_URL", "GOOGLE_OAUTH_REDIRECT_URI"):
        if os.getenv(name) and urlparse(os.environ[name]).scheme != "https":
            errors.append(f"{name} must use https")
    site_url = os.getenv("SITE_URL", "").rstrip("/")
    cors = {item.strip().rstrip("/") for item in os.getenv("CORS_ORIGINS", "").split(",") if item.strip()}
    if site_url and site_url not in cors:
        errors.append("CORS_ORIGINS must include SITE_URL exactly")
    if any(os.getenv(name, "false").lower() == "true" for name in ("NAUTILUS_LIVE_TRADING_ENABLED", "NAUTILUS_ALLOW_LIVE_ORDER", "NAUTILUS_ALLOW_WITHDRAWAL", "NAUTILUS_ALLOW_TRANSFER")):
        errors.append("LIVE, withdrawal, and transfer flags must remain false")
    if errors:
        print("Production environment invalid:")
        for error in errors: print(f"- {error}")
        return 1
    print("Production environment valid (secret values redacted)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
