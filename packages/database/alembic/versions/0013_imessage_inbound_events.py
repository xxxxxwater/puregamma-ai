"""add idempotent inbound iMessage relay events

Revision ID: 0013_imessage_inbound_events
Revises: 0012_mobile_web_sessions
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_imessage_inbound_events"
down_revision = "0012_mobile_web_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "imessage_inbound_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("relay_message_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("assistant_message_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assistant_message_id"], ["agent_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("relay_message_id"),
    )
    op.create_index("ix_imessage_inbound_events_relay_message_id", "imessage_inbound_events", ["relay_message_id"])
    op.create_index("ix_imessage_inbound_events_user_id", "imessage_inbound_events", ["user_id"])
    op.create_index("ix_imessage_inbound_events_status", "imessage_inbound_events", ["status"])


def downgrade() -> None:
    op.drop_index("ix_imessage_inbound_events_status", table_name="imessage_inbound_events")
    op.drop_index("ix_imessage_inbound_events_user_id", table_name="imessage_inbound_events")
    op.drop_index("ix_imessage_inbound_events_relay_message_id", table_name="imessage_inbound_events")
    op.drop_table("imessage_inbound_events")
