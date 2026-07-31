"""portfolio-aware daily brief idempotency

Revision ID: 0003_portfolio_daily_brief
Revises: 0002_agent_metering
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_portfolio_daily_brief"
down_revision = "0002_agent_metering"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_preferences") as batch:
        batch.add_column(sa.Column("include_portfolio_in_ai", sa.Boolean(), nullable=False, server_default=sa.true()))
    with op.batch_alter_table("reports") as batch:
        batch.add_column(sa.Column("report_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("status", sa.String(), nullable=False, server_default="completed"))
        batch.add_column(sa.Column("idempotency_key", sa.String(), nullable=True))
        batch.add_column(sa.Column("error_message", sa.Text(), nullable=True))
        batch.create_index("ix_reports_report_date", ["report_date"], unique=False)
        batch.create_index("ix_reports_status", ["status"], unique=False)
        batch.create_index("ix_reports_idempotency_key", ["idempotency_key"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("reports") as batch:
        batch.drop_index("ix_reports_idempotency_key")
        batch.drop_index("ix_reports_status")
        batch.drop_index("ix_reports_report_date")
        batch.drop_column("error_message")
        batch.drop_column("idempotency_key")
        batch.drop_column("status")
        batch.drop_column("report_date")
    with op.batch_alter_table("user_preferences") as batch:
        batch.drop_column("include_portfolio_in_ai")
