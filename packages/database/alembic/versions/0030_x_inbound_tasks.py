"""add persistent X (Twitter) DM inbound tasks

Revision ID: 0030_x_inbound_tasks
Revises: 0029_photon_inbound_tasks
"""

from alembic import op
import sqlalchemy as sa


revision = "0030_x_inbound_tasks"
down_revision = "0029_photon_inbound_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent for the same reason as 0027/0028/0029: local/dev schemas
    # created with create_all may already carry the table.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "x_inbound_tasks" in inspector.get_table_names():
        return
    op.create_table(
        "x_inbound_tasks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("x_event_id", sa.String(), nullable=False),
        sa.Column("sender_x_id", sa.String(), nullable=False),
        sa.Column("conversation_key", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("assistant_message_id", sa.String(), nullable=True),
        sa.Column("outbound_delivery_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assistant_message_id"], ["agent_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["outbound_delivery_id"], ["notification_deliveries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("x_event_id", name="uq_x_inbound_event_id"),
    )
    op.create_index("ix_x_inbound_tasks_x_event_id", "x_inbound_tasks", ["x_event_id"])
    op.create_index("ix_x_inbound_tasks_status", "x_inbound_tasks", ["status"])
    op.create_index("ix_x_inbound_tasks_next_retry_at", "x_inbound_tasks", ["next_retry_at"])


def downgrade() -> None:
    op.drop_index("ix_x_inbound_tasks_next_retry_at", table_name="x_inbound_tasks")
    op.drop_index("ix_x_inbound_tasks_status", table_name="x_inbound_tasks")
    op.drop_index("ix_x_inbound_tasks_x_event_id", table_name="x_inbound_tasks")
    op.drop_table("x_inbound_tasks")
