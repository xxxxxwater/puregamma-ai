"""research run credit reservation/settlement columns

Revision ID: 0022_research_run_billing
Revises: 0021_custody
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_research_run_billing"
down_revision = "0021_custody"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_runs",
        sa.Column("credits_reserved", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "research_runs",
        sa.Column("credits_spent", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("research_runs", "credits_spent")
    op.drop_column("research_runs", "credits_reserved")
