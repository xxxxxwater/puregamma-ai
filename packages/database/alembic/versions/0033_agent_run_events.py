"""agent run events: the durable, sequenced transcript of a run

Revision ID: 0033_agent_run_events
Revises: 0032_chat_workspace
Create Date: 2026-09-24

Additive only. A run's events are written best-effort while it streams, so this
table being empty for an old run is normal and must never be treated as an
error: the reader returns whatever exists and the caller falls back to the
persisted message.

The unique (run_id, seq) is what makes a replay safe - a sequence number is
never reused, so a client resuming from its own cursor cannot see a duplicate or
skip an event.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_agent_run_events"
down_revision = "0032_chat_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_run_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("data_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "seq", name="uq_agent_run_event_seq"),
    )
    op.create_index("ix_agent_run_events_run_id", "agent_run_events", ["run_id"])
    op.create_index("ix_agent_run_events_type", "agent_run_events", ["type"])
    op.create_index("ix_agent_run_events_created_at", "agent_run_events", ["created_at"])


def downgrade() -> None:
    # Dropping the table loses only replayable transcript detail; the messages
    # and tool calls a run produced live in their own tables and are untouched.
    op.drop_index("ix_agent_run_events_created_at", table_name="agent_run_events")
    op.drop_index("ix_agent_run_events_type", table_name="agent_run_events")
    op.drop_index("ix_agent_run_events_run_id", table_name="agent_run_events")
    op.drop_table("agent_run_events")
