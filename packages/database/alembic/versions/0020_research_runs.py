"""isolated python research runner runs

Revision ID: 0020_research_runs
Revises: 0019_daily_brief_channels
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_research_runs"
down_revision = "0019_daily_brief_channels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("dataset_refs_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("limits_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("metrics_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("figures_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("logs", sa.Text(), nullable=False, server_default=""),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_research_run_idempotency"),
    )
    op.create_index("ix_research_runs_user_id", "research_runs", ["user_id"])
    op.create_index("ix_research_runs_status", "research_runs", ["status"])
    op.create_index("ix_research_runs_code_hash", "research_runs", ["code_hash"])
    op.create_index("ix_research_runs_idempotency_key", "research_runs", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_research_runs_idempotency_key", table_name="research_runs")
    op.drop_index("ix_research_runs_code_hash", table_name="research_runs")
    op.drop_index("ix_research_runs_status", table_name="research_runs")
    op.drop_index("ix_research_runs_user_id", table_name="research_runs")
    op.drop_table("research_runs")
