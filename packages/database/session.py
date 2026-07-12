from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

from apps.api.config import get_settings
from packages.database.models import Base


def _engine_kwargs(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


settings = get_settings()
engine = create_engine(settings.database_url, future=True, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_compat_columns()


def ensure_compat_columns() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    additions = [
        ("user_preferences", "locale", "VARCHAR NOT NULL DEFAULT 'en'"),
        ("user_preferences", "subscription_cancel_at_period_end", "BOOLEAN NOT NULL DEFAULT 0"),
        ("user_preferences", "subscription_cancel_at", "DATETIME"),
        ("users", "google_user_id", "VARCHAR"),
        ("users", "avatar_url", "VARCHAR"),
        ("users", "auth_provider", "VARCHAR NOT NULL DEFAULT 'mock'"),
        ("users", "email_verified_at", "DATETIME"),
        ("users", "last_login_at", "DATETIME"),
        ("users", "session_version", "INTEGER NOT NULL DEFAULT 0"),
        ("reports", "language", "VARCHAR NOT NULL DEFAULT 'en'"),
        ("notification_deliveries", "locale", "VARCHAR NOT NULL DEFAULT 'en'"),
        ("agent_messages", "context_json", "JSON NOT NULL DEFAULT '{}'"),
        ("exchange_connections", "credential_ciphertext", "TEXT"),
        ("user_preferences", "portfolio_autopilot_json", "JSON NOT NULL DEFAULT '{}'"),
        ("stripe_webhook_events", "requires_manual_review", "BOOLEAN NOT NULL DEFAULT 0"),
        ("stripe_webhook_events", "error_message", "TEXT"),
    ]
    with engine.begin() as connection:
        for table, column, ddl_type in additions:
            if table not in existing_tables:
                continue
            columns = {item["name"] for item in inspector.get_columns(table)}
            if column not in columns:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def drop_db() -> None:
    Base.metadata.drop_all(bind=engine)
