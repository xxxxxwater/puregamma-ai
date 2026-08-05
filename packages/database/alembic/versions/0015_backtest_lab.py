"""add backtest lab candles and runs

Revision ID: 0015_backtest_lab
Revises: 0014_user_email_auth
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_backtest_lab"
down_revision = "0014_user_email_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backtest_candles",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("interval", sa.String(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "interval", "ts", name="uq_backtest_candle_symbol_interval_ts"),
    )
    op.create_index("ix_backtest_candles_symbol", "backtest_candles", ["symbol"])
    op.create_index("ix_backtest_candles_ts", "backtest_candles", ["ts"])

    op.create_table(
        "backtest_lab_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("spec_json", sa.JSON(), nullable=False),
        sa.Column("symbols_json", sa.JSON(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("performance_json", sa.JSON(), nullable=False),
        sa.Column("equity_json", sa.JSON(), nullable=False),
        sa.Column("assumptions_json", sa.JSON(), nullable=False),
        sa.Column("context_used_json", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("credits_spent", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_backtest_lab_runs_user_id", "backtest_lab_runs", ["user_id"])
    op.create_index("ix_backtest_lab_runs_status", "backtest_lab_runs", ["status"])
    op.create_index("ix_backtest_lab_runs_idempotency_key", "backtest_lab_runs", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_backtest_lab_runs_idempotency_key", table_name="backtest_lab_runs")
    op.drop_index("ix_backtest_lab_runs_status", table_name="backtest_lab_runs")
    op.drop_index("ix_backtest_lab_runs_user_id", table_name="backtest_lab_runs")
    op.drop_table("backtest_lab_runs")
    op.drop_index("ix_backtest_candles_ts", table_name="backtest_candles")
    op.drop_index("ix_backtest_candles_symbol", table_name="backtest_candles")
    op.drop_table("backtest_candles")
