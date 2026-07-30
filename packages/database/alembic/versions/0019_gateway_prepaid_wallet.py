"""add a prepaid wallet dedicated to API Gateway traffic

Revision ID: 0019_gateway_prepaid_wallet
Revises: 0018_ai_gateway
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_gateway_prepaid_wallet"
down_revision = "0018_ai_gateway"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gateway_wallets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("available_balance_usd", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("lifetime_credited_usd", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("lifetime_debited_usd", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_gateway_wallets_user_id", "gateway_wallets", ["user_id"])

    op.create_table(
        "gateway_topup_intents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("public_reference", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(), nullable=False, server_default="created"),
        sa.Column("stripe_checkout_session_id", sa.String(), nullable=True),
        sa.Column("stripe_payment_intent_id", sa.String(), nullable=True),
        sa.Column("stripe_customer_id", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_reference"),
        sa.UniqueConstraint("stripe_checkout_session_id"),
        sa.UniqueConstraint("stripe_payment_intent_id"),
    )
    for name, columns in (
        ("ix_gateway_topup_intents_public_reference", ["public_reference"]),
        ("ix_gateway_topup_intents_user_id", ["user_id"]),
        ("ix_gateway_topup_intents_status", ["status"]),
        ("ix_gateway_topup_intents_stripe_checkout_session_id", ["stripe_checkout_session_id"]),
        ("ix_gateway_topup_intents_stripe_payment_intent_id", ["stripe_payment_intent_id"]),
        ("ix_gateway_topup_intents_stripe_customer_id", ["stripe_customer_id"]),
        ("ix_gateway_topup_intents_created_at", ["created_at"]),
    ):
        op.create_index(name, "gateway_topup_intents", columns)

    op.create_table(
        "gateway_wallet_ledger",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("wallet_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("entry_type", sa.String(), nullable=False),
        sa.Column("amount_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("balance_after_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("topup_intent_id", sa.String(), nullable=True),
        sa.Column("gateway_request_log_id", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["wallet_id"], ["gateway_wallets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topup_intent_id"], ["gateway_topup_intents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["gateway_request_log_id"], ["gateway_request_logs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("topup_intent_id"),
        sa.UniqueConstraint("gateway_request_log_id"),
    )
    for name, columns in (
        ("ix_gateway_wallet_ledger_wallet_id", ["wallet_id"]),
        ("ix_gateway_wallet_ledger_user_id", ["user_id"]),
        ("ix_gateway_wallet_ledger_entry_type", ["entry_type"]),
        ("ix_gateway_wallet_ledger_idempotency_key", ["idempotency_key"]),
        ("ix_gateway_wallet_ledger_topup_intent_id", ["topup_intent_id"]),
        ("ix_gateway_wallet_ledger_gateway_request_log_id", ["gateway_request_log_id"]),
        ("ix_gateway_wallet_ledger_created_at", ["created_at"]),
    ):
        op.create_index(name, "gateway_wallet_ledger", columns)


def downgrade() -> None:
    op.drop_table("gateway_wallet_ledger")
    op.drop_table("gateway_topup_intents")
    op.drop_table("gateway_wallets")
