"""unify research backtests and add durable artifacts

Revision ID: 0016_unified_backtest_artifacts
Revises: 0015_backtest_lab
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_unified_backtest_artifacts"
down_revision = "0015_backtest_lab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("backtest_runs") as batch:
        batch.add_column(sa.Column("status", sa.String(), nullable=False, server_default="completed"))
        batch.add_column(sa.Column("engine", sa.String(), nullable=False, server_default="vectorbt"))
        batch.add_column(sa.Column("strategy_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("strategy_version", sa.String(), nullable=True))
        batch.add_column(sa.Column("spec_json", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("data_snapshot_json", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("assumptions_json", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("error_json", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("credits_reserved", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_backtest_runs_status", ["status"])
        batch.create_index("ix_backtest_runs_strategy_id", ["strategy_id"])

    op.create_table(
        "backtest_artifacts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("backtest_id", sa.String(), nullable=False),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("format", sa.String(), nullable=False),
        sa.Column("relative_path", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(), nullable=True),
        sa.Column("credits_spent", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["backtest_id"], ["backtest_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backtest_artifacts_user_id", "backtest_artifacts", ["user_id"])
    op.create_index("ix_backtest_artifacts_backtest_id", "backtest_artifacts", ["backtest_id"])
    op.create_index("ix_backtest_artifacts_artifact_type", "backtest_artifacts", ["artifact_type"])


def downgrade() -> None:
    op.drop_index("ix_backtest_artifacts_artifact_type", table_name="backtest_artifacts")
    op.drop_index("ix_backtest_artifacts_backtest_id", table_name="backtest_artifacts")
    op.drop_index("ix_backtest_artifacts_user_id", table_name="backtest_artifacts")
    op.drop_table("backtest_artifacts")
    with op.batch_alter_table("backtest_runs") as batch:
        batch.drop_index("ix_backtest_runs_strategy_id")
        batch.drop_index("ix_backtest_runs_status")
        for name in ("completed_at", "credits_reserved", "error_json", "assumptions_json", "data_snapshot_json", "spec_json", "strategy_version", "strategy_id", "engine", "status"):
            batch.drop_column(name)
