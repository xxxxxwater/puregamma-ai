from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from apps.api.config import get_settings
from packages.database.models import Base


ROOT = Path(__file__).resolve().parents[2]


def _engine_kwargs(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


settings = get_settings()
engine = create_engine(
    settings.database_url, future=True, pool_pre_ping=True, **_engine_kwargs(settings.database_url)
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


POST_BASELINE_COLUMNS = {
    ("credit_ledger", "idempotency_key"),
    ("agent_runs", "credit_cost"),
    ("agent_runs", "credit_refunded"),
    ("agent_runs", "queue_priority"),
    ("user_preferences", "include_portfolio_in_ai"),
    ("reports", "report_date"),
    ("reports", "status"),
    ("reports", "idempotency_key"),
    ("reports", "error_message"),
}


def _schema_gaps(*, ignore_columns: set[tuple[str, str]] | None = None) -> list[str]:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    ignore_columns = ignore_columns or set()
    gaps: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            gaps.append(f"missing table {table.name}")
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if (table.name, column.name) in ignore_columns:
                continue
            if column.name not in existing_columns:
                gaps.append(f"missing column {table.name}.{column.name}")
    return gaps


def _baseline_schema_gaps() -> list[str]:
    return _schema_gaps(ignore_columns=POST_BASELINE_COLUMNS)


def upgrade_database(*, allow_stamp_existing: bool = True) -> None:
    """Upgrade to Alembic head and safely adopt pre-Alembic current schemas.

    A non-empty database is stamped only when every current ORM table and column
    already exists. Older or partial schemas fail closed and require an explicit
    reviewed migration instead of receiving opportunistic ALTER TABLE statements.
    """
    config = _alembic_config()
    tables = set(inspect(engine).get_table_names())
    has_version = "alembic_version" in tables
    application_tables = tables - {"alembic_version"}
    if application_tables and not has_version:
        if not allow_stamp_existing:
            raise RuntimeError(
                "Existing database has no Alembic version. Run the reviewed baseline adoption command."
            )
        gaps = _baseline_schema_gaps()
        if gaps:
            preview = "; ".join(gaps[:20])
            raise RuntimeError(
                "Existing database does not match the Alembic baseline: " + preview
            )
        command.stamp(config, "0001_baseline")
    command.upgrade(config, "head")


def init_db() -> None:
    upgrade_database()


def drop_db() -> None:
    Base.metadata.drop_all(bind=engine)
