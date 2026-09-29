#!/usr/bin/env python3
"""Fail-fast, redacted production environment validation.

This script is intentionally usable on a bare deployment host before the
application containers start. --env-file is parsed without executing shell
code, so production validation cannot be skipped merely because variables were
only present in Compose's .env file.
"""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from urllib.parse import urlparse

_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _load_env_file(path: str) -> list[str]:
    """Load a Compose-style env file without evaluating shell expressions."""
    env_path = Path(path)
    if not env_path.is_file():
        return [f"Environment file not found: {env_path}"]

    parsed: dict[str, str] = {}
    errors: list[str] = []
    for lineno, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            errors.append(f"{env_path}:{lineno}: expected KEY=VALUE")
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            errors.append(f"{env_path}:{lineno}: invalid environment key")
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        def expand(match: re.Match[str]) -> str:
            name = match.group(1)
            return parsed.get(name, os.environ.get(name, ""))

        parsed[key] = _VAR.sub(expand, value)

    if errors:
        return errors
    os.environ.update(parsed)
    return []


def _deployment_checks() -> list[str]:
    errors: list[str] = []
    required = (
        "DATABASE_URL",
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "REDIS_URL",
        "JWT_SECRET",
        "SESSION_SECRET",
        "ENCRYPTION_MASTER_KEY",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "NEXT_PUBLIC_API_URL",
        "SITE_URL",
        "APP_DOMAIN",
        "API_DOMAIN",
        "CORS_ORIGINS",
        "SESSION_COOKIE_DOMAIN",
        "GOOGLE_OAUTH_REDIRECT_URI",
        "INTERNAL_RUNTIME_SECRET",
        "METRICS_BEARER_TOKEN",
        "NAUTILUS_RUNTIME_SECRET",
        "LLM_PROVIDER",
        "IMESSAGE_PROVIDER",
    )
    for name in required:
        value = os.getenv(name, "")
        if not value or value.lower() in {"change-me", "dev-only-change-me", "dev-runtime-secret"}:
            errors.append(f"{name} is required")

    for name in (
        "JWT_SECRET",
        "SESSION_SECRET",
        "ENCRYPTION_MASTER_KEY",
        "INTERNAL_RUNTIME_SECRET",
    ):
        value = os.getenv(name, "")
        if value and len(value) < 32:
            errors.append(f"{name} must be at least 32 characters")

    for name in ("POSTGRES_PASSWORD", "REDIS_PASSWORD"):
        value = os.getenv(name, "")
        if value and len(value) < 16:
            errors.append(f"{name} must be at least 16 characters")

    if os.getenv("NAUTILUS_RUNTIME_SECRET", "") and len(os.environ["NAUTILUS_RUNTIME_SECRET"]) < 24:
        errors.append("NAUTILUS_RUNTIME_SECRET must be at least 24 characters")

    if not os.getenv("DATABASE_URL", "").startswith(("postgresql://", "postgresql+psycopg://")):
        errors.append("DATABASE_URL must use PostgreSQL")

    if os.getenv("AUTH_ALLOW_DEMO_FALLBACK", "false").lower() == "true":
        errors.append("AUTH_ALLOW_DEMO_FALLBACK must be false")
    if os.getenv("NEXT_PUBLIC_ALLOW_MOCK_FALLBACK", "false").lower() == "true":
        errors.append("NEXT_PUBLIC_ALLOW_MOCK_FALLBACK must be false")
    if any(
        os.getenv(name, "false").lower() == "true"
        for name in ("ENABLE_MOCK_AGENT", "ENABLE_MOCK_MARKET_DATA", "ENABLE_MOCK_DATA_SOURCES")
    ):
        errors.append("mock providers must be disabled in production")

    for name in (
        "NEXT_PUBLIC_API_URL",
        "SITE_URL",
        "GOOGLE_OAUTH_REDIRECT_URI",
        "STRIPE_SUCCESS_URL",
        "STRIPE_CANCEL_URL",
    ):
        value = os.getenv(name, "")
        if value and urlparse(value).scheme != "https":
            errors.append(f"{name} must use https")

    app_domain = os.getenv("APP_DOMAIN", "").strip().lower()
    api_domain = os.getenv("API_DOMAIN", "").strip().lower()
    site_host = (urlparse(os.getenv("SITE_URL", "")).hostname or "").lower()
    api_host = (urlparse(os.getenv("NEXT_PUBLIC_API_URL", "")).hostname or "").lower()
    if app_domain and site_host and app_domain != site_host:
        errors.append("SITE_URL host must match APP_DOMAIN")
    if api_domain and api_host and api_domain != api_host:
        errors.append("NEXT_PUBLIC_API_URL host must match API_DOMAIN")
    if app_domain and api_domain and app_domain == api_domain:
        errors.append("APP_DOMAIN and API_DOMAIN must be distinct")

    cors = {
        item.strip().rstrip("/")
        for item in os.getenv("CORS_ORIGINS", "").split(",")
        if item.strip()
    }
    site_url = os.getenv("SITE_URL", "").rstrip("/")
    if site_url and site_url not in cors:
        errors.append("CORS_ORIGINS must include SITE_URL exactly")
    if "*" in cors or any("localhost" in item or "127.0.0.1" in item for item in cors):
        errors.append("CORS_ORIGINS must not contain wildcard or localhost origins in production")

    if any(
        os.getenv(name, "false").lower() == "true"
        for name in (
            "NAUTILUS_LIVE_TRADING_ENABLED",
            "NAUTILUS_ALLOW_LIVE_ORDER",
            "NAUTILUS_ALLOW_WITHDRAWAL",
            "NAUTILUS_ALLOW_TRANSFER",
        )
    ):
        errors.append("legacy LIVE, withdrawal, and transfer flags must remain false")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", help="Compose-style environment file to validate")
    parser.add_argument(
        "--require-production",
        action="store_true",
        help="fail instead of skipping when APP_ENV is not production",
    )
    args = parser.parse_args(argv)

    errors: list[str] = []
    if args.env_file:
        errors.extend(_load_env_file(args.env_file))
        if errors:
            print("Production environment invalid:")
            for error in errors:
                print(f"- {error}")
            return 1

    app_env = os.getenv("APP_ENV", "development").lower()
    if app_env not in {"production", "prod"}:
        if args.require_production:
            print("Production environment invalid:")
            print("- APP_ENV must be production")
            return 1
        print("APP_ENV is not production; validation skipped")
        return 0

    if app_env == "prod":
        os.environ["APP_ENV"] = "production"

    errors.extend(_deployment_checks())

    try:
        from apps.api.config import Settings, validate_production_settings

        validate_production_settings(Settings())
    except RuntimeError as exc:
        message = str(exc)
        prefix = "Invalid production configuration: "
        if message.startswith(prefix):
            errors.extend(part.strip() for part in message[len(prefix):].split(";") if part.strip())
        else:
            errors.append(message)
    except Exception as exc:
        errors.append(f"application configuration validation failed: {type(exc).__name__}: {exc}")

    errors = list(dict.fromkeys(errors))
    if errors:
        print("Production environment invalid:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Production environment valid (secret values redacted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
