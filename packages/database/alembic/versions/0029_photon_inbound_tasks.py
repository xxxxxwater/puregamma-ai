"""add persistent photon inbound tasks

Revision ID: 0029_photon_inbound_tasks
Revises: 0028_user_memory_consent
"""

from alembic import op
import sqlalchemy as sa


revision = "0029_photon_inbound_tasks"
down_revision = "0028_user_memory_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent for the same reason as 0027/0028: local/dev schemas created
    # with create_all may already carry the table.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "photon_inbound_tasks" in inspector.get_table_names():
        return
    op.create_table(
        "photon_inbound_tasks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("sender", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("outbound_delivery_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["outbound_delivery_id"], ["notification_deliveries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_photon_inbound_message_id"),
    )
    op.create_index("ix_photon_inbound_tasks_message_id", "photon_inbound_tasks", ["message_id"])
    op.create_index("ix_photon_inbound_tasks_status", "photon_inbound_tasks", ["status"])
    op.create_index("ix_photon_inbound_tasks_next_retry_at", "photon_inbound_tasks", ["next_retry_at"])


def downgrade() -> None:
    op.drop_index("ix_photon_inbound_tasks_next_retry_at", table_name="photon_inbound_tasks")
    op.drop_index("ix_photon_inbound_tasks_status", table_name="photon_inbound_tasks")
    op.drop_index("ix_photon_inbound_tasks_message_id", table_name="photon_inbound_tasks")
    op.drop_table("photon_inbound_tasks")
