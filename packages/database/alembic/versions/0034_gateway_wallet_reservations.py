"""hold prepaid Gateway USD for in-flight requests

Revision ID: 0034_gateway_wallet_reservations
Revises: 0033_agent_run_events
"""

from alembic import op
import sqlalchemy as sa


revision = "0034_gateway_wallet_reservations"
down_revision = "0033_agent_run_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gateway_wallets",
        sa.Column("reserved_usd", sa.Numeric(18, 8), nullable=False, server_default="0"),
    )

    op.create_table(
        "gateway_request_reservations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("wallet_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("amount_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="held"),
        sa.Column("settled_amount_usd", sa.Numeric(18, 8), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["wallet_id"], ["gateway_wallets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    for name, columns in (
        ("ix_gateway_request_reservations_request_id", ["request_id"]),
        ("ix_gateway_request_reservations_wallet_id", ["wallet_id"]),
        ("ix_gateway_request_reservations_user_id", ["user_id"]),
        ("ix_gateway_request_reservations_status", ["status"]),
        ("ix_gateway_request_reservations_created_at", ["created_at"]),
    ):
        op.create_index(name, "gateway_request_reservations", columns)


def downgrade() -> None:
    for name in (
        "ix_gateway_request_reservations_request_id",
        "ix_gateway_request_reservations_wallet_id",
        "ix_gateway_request_reservations_user_id",
        "ix_gateway_request_reservations_status",
        "ix_gateway_request_reservations_created_at",
    ):
        op.drop_index(name, table_name="gateway_request_reservations")
    op.drop_table("gateway_request_reservations")
    op.drop_column("gateway_wallets", "reserved_usd")
