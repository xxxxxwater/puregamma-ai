"""custody domain: accounts, sub-ledger, deposits, withdrawals, reconciliations

Revision ID: 0021_custody
Revises: 0020_research_runs
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_custody"
down_revision = "0020_research_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custody_accounts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("venue", sa.String(), nullable=False),
        sa.Column("environment", sa.String(), nullable=False, server_default="testnet"),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("deposit_address", sa.String(), nullable=True),
        sa.Column("provider_ref", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_custody_accounts_venue", "custody_accounts", ["venue"])
    op.create_index("ix_custody_accounts_status", "custody_accounts", ["status"])

    op.create_table(
        "custody_sub_accounts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("custody_account_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("asset", sa.String(), nullable=False),
        sa.Column("available", sa.Numeric(38, 18), nullable=False, server_default="0"),
        sa.Column("frozen", sa.Numeric(38, 18), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["custody_account_id"], ["custody_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("custody_account_id", "user_id", "asset", name="uq_custody_sub_account"),
    )
    op.create_index("ix_custody_sub_accounts_user_id", "custody_sub_accounts", ["user_id"])

    op.create_table(
        "custody_ledger_entries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("sub_account_id", sa.String(), nullable=False),
        sa.Column("entry_type", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(38, 18), nullable=False),
        sa.Column("available_after", sa.Numeric(38, 18), nullable=False),
        sa.Column("frozen_after", sa.Numeric(38, 18), nullable=False),
        sa.Column("ref_type", sa.String(), nullable=True),
        sa.Column("ref_id", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["sub_account_id"], ["custody_sub_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_custody_ledger_idempotency"),
    )
    op.create_index("ix_custody_ledger_sub_account", "custody_ledger_entries", ["sub_account_id"])
    op.create_index("ix_custody_ledger_entry_type", "custody_ledger_entries", ["entry_type"])

    op.create_table(
        "custody_deposits",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("sub_account_id", sa.String(), nullable=False),
        sa.Column("asset", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(38, 18), nullable=False),
        sa.Column("tx_ref", sa.String(), nullable=False),
        sa.Column("confirmations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("external_ref", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["sub_account_id"], ["custody_sub_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_ref", name="uq_custody_deposit_external_ref"),
    )
    op.create_index("ix_custody_deposits_sub_account", "custody_deposits", ["sub_account_id"])
    op.create_index("ix_custody_deposits_status", "custody_deposits", ["status"])

    op.create_table(
        "custody_withdrawals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("sub_account_id", sa.String(), nullable=False),
        sa.Column("asset", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(38, 18), nullable=False),
        sa.Column("address", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="intent"),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("tx_ref", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["sub_account_id"], ["custody_sub_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_custody_withdrawal_idempotency"),
    )
    op.create_index("ix_custody_withdrawals_sub_account", "custody_withdrawals", ["sub_account_id"])
    op.create_index("ix_custody_withdrawals_status", "custody_withdrawals", ["status"])

    op.create_table(
        "custody_reconciliations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("custody_account_id", sa.String(), nullable=False),
        sa.Column("asset", sa.String(), nullable=False),
        sa.Column("local_available", sa.Numeric(38, 18), nullable=False),
        sa.Column("local_frozen", sa.Numeric(38, 18), nullable=False),
        sa.Column("external_balance", sa.Numeric(38, 18), nullable=True),
        sa.Column("difference", sa.Numeric(38, 18), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("details_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["custody_account_id"], ["custody_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_custody_reconciliations_account", "custody_reconciliations", ["custody_account_id"])


def downgrade() -> None:
    op.drop_table("custody_reconciliations")
    op.drop_table("custody_withdrawals")
    op.drop_table("custody_deposits")
    op.drop_table("custody_ledger_entries")
    op.drop_table("custody_sub_accounts")
    op.drop_table("custody_accounts")
