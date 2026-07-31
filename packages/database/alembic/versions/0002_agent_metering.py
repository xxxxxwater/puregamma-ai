"""agent metering and credit idempotency

Revision ID: 0002_agent_metering
Revises: 0001_baseline
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_agent_metering"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("credit_ledger") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(), nullable=True))
        batch.create_index("ix_credit_ledger_idempotency_key", ["idempotency_key"], unique=True)
    with op.batch_alter_table("agent_runs") as batch:
        batch.add_column(sa.Column("credit_cost", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("credit_refunded", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("queue_priority", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_column("queue_priority")
        batch.drop_column("credit_refunded")
        batch.drop_column("credit_cost")
    with op.batch_alter_table("credit_ledger") as batch:
        batch.drop_index("ix_credit_ledger_idempotency_key")
        batch.drop_column("idempotency_key")
