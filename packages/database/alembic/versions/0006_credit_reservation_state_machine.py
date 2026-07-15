"""persisted credit reservation and settlement state machine

Revision ID: 0006_credit_state_machine
Revises: 0005_imessage_delivery_retries
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_credit_state_machine"
down_revision = "0005_imessage_delivery_retries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "credit_balance",
            existing_type=sa.Integer(),
            server_default="150",
            existing_nullable=False,
        )
    with op.batch_alter_table("backtest_runs") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(), nullable=True))
        batch.create_index("ix_backtest_runs_idempotency_key", ["idempotency_key"], unique=True)

    op.create_table(
        "credit_reservations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="RESERVED"),
        sa.Column("reserved_credits", sa.Integer(), nullable=False),
        sa.Column("settled_credits", sa.Integer(), nullable=True),
        sa.Column("quote_json", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("ledger_entry_id", sa.String(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ledger_entry_id"], ["credit_ledger.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_credit_reservations_user_id", "credit_reservations", ["user_id"])
    op.create_index("ix_credit_reservations_task_type", "credit_reservations", ["task_type"])
    op.create_index("ix_credit_reservations_status", "credit_reservations", ["status"])
    op.create_index("ix_credit_reservations_idempotency_key", "credit_reservations", ["idempotency_key"], unique=True)

    op.create_table(
        "credit_settlements",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("reservation_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("requested_actual_credits", sa.Integer(), nullable=False),
        sa.Column("settled_credits", sa.Integer(), nullable=False),
        sa.Column("adjustment", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="SETTLED"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["reservation_id"], ["credit_reservations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reservation_id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_credit_settlements_reservation_id", "credit_settlements", ["reservation_id"], unique=True)
    op.create_index("ix_credit_settlements_user_id", "credit_settlements", ["user_id"])
    op.create_index("ix_credit_settlements_idempotency_key", "credit_settlements", ["idempotency_key"], unique=True)

    op.create_table(
        "credit_refund_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("reservation_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["reservation_id"], ["credit_reservations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reservation_id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_credit_refund_events_reservation_id", "credit_refund_events", ["reservation_id"], unique=True)
    op.create_index("ix_credit_refund_events_user_id", "credit_refund_events", ["user_id"])
    op.create_index("ix_credit_refund_events_idempotency_key", "credit_refund_events", ["idempotency_key"], unique=True)

    op.create_table(
        "credit_budget_policies",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("automation_key", sa.String(), nullable=False),
        sa.Column("daily_limit", sa.Integer(), nullable=False),
        sa.Column("monthly_limit", sa.Integer(), nullable=False),
        sa.Column("per_run_limit", sa.Integer(), nullable=False),
        sa.Column("alert_threshold_pct", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pause_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "automation_key", name="uq_credit_budget_user_automation"),
    )
    op.create_index("ix_credit_budget_policies_user_id", "credit_budget_policies", ["user_id"])
    op.create_index("ix_credit_budget_policies_automation_key", "credit_budget_policies", ["automation_key"])

    op.create_table(
        "credit_reward_grants",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("reward_type", sa.String(), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("granted_by_user_id", sa.String(), nullable=True),
        sa.Column("ledger_entry_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ledger_entry_id"], ["credit_ledger.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_credit_reward_grants_user_id", "credit_reward_grants", ["user_id"])
    op.create_index("ix_credit_reward_grants_reward_type", "credit_reward_grants", ["reward_type"])
    op.create_index("ix_credit_reward_grants_idempotency_key", "credit_reward_grants", ["idempotency_key"], unique=True)
    op.create_index("ix_credit_reward_grants_created_at", "credit_reward_grants", ["created_at"])


def downgrade() -> None:
    op.drop_table("credit_reward_grants")
    op.drop_table("credit_budget_policies")
    op.drop_table("credit_refund_events")
    op.drop_table("credit_settlements")
    op.drop_table("credit_reservations")
    with op.batch_alter_table("backtest_runs") as batch:
        batch.drop_index("ix_backtest_runs_idempotency_key")
        batch.drop_column("idempotency_key")
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "credit_balance",
            existing_type=sa.Integer(),
            server_default=None,
            existing_nullable=False,
        )
