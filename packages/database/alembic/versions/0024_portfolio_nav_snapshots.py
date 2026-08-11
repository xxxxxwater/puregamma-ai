"""daily per-user portfolio NAV snapshots

Revision ID: 0024_portfolio_nav_snapshots
Revises: 0019_gateway_prepaid_wallet
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_portfolio_nav_snapshots"
down_revision = "0019_gateway_prepaid_wallet"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_nav_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("total_nav", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cash_balance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("account_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("positions_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_accounts_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("partial", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("data_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "snapshot_date", name="uq_portfolio_nav_user_date"),
    )
    for name, columns in (
        ("ix_portfolio_nav_snapshots_user_id", ["user_id"]),
        ("ix_portfolio_nav_snapshots_snapshot_date", ["snapshot_date"]),
        ("ix_portfolio_nav_snapshots_captured_at", ["captured_at"]),
    ):
        op.create_index(name, "portfolio_nav_snapshots", columns)


def downgrade() -> None:
    op.drop_table("portfolio_nav_snapshots")
