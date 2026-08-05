"""persist Plaid investment transactions for portfolio NAV

Revision ID: 0017_plaid_investment_tx
Revises: 0016_unified_backtest_artifacts
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_plaid_investment_tx"
down_revision = "0016_unified_backtest_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_investment_transactions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("provider_account_id", sa.String(), nullable=False),
        sa.Column("security_id", sa.String(), nullable=True),
        sa.Column("posted_date", sa.Date(), nullable=False),
        sa.Column("transaction_datetime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=True),
        sa.Column("transaction_type", sa.String(), nullable=False),
        sa.Column("subtype", sa.String(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fees", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(), nullable=True),
        sa.Column("cancelled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("raw_event_reference", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["trading_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "provider", "external_id", name="uq_portfolio_investment_transaction_external"),
    )
    op.create_index("ix_portfolio_investment_transactions_user_id", "portfolio_investment_transactions", ["user_id"])
    op.create_index("ix_portfolio_investment_transactions_account_id", "portfolio_investment_transactions", ["account_id"])
    op.create_index("ix_portfolio_investment_transactions_provider", "portfolio_investment_transactions", ["provider"])
    op.create_index("ix_portfolio_investment_transactions_provider_account_id", "portfolio_investment_transactions", ["provider_account_id"])
    op.create_index("ix_portfolio_investment_transactions_security_id", "portfolio_investment_transactions", ["security_id"])
    op.create_index("ix_portfolio_investment_transactions_posted_date", "portfolio_investment_transactions", ["posted_date"])
    op.create_index("ix_portfolio_investment_transactions_symbol", "portfolio_investment_transactions", ["symbol"])


def downgrade() -> None:
    for name in (
        "ix_portfolio_investment_transactions_symbol",
        "ix_portfolio_investment_transactions_posted_date",
        "ix_portfolio_investment_transactions_security_id",
        "ix_portfolio_investment_transactions_provider_account_id",
        "ix_portfolio_investment_transactions_provider",
        "ix_portfolio_investment_transactions_account_id",
        "ix_portfolio_investment_transactions_user_id",
    ):
        op.drop_index(name, table_name="portfolio_investment_transactions")
    op.drop_table("portfolio_investment_transactions")
