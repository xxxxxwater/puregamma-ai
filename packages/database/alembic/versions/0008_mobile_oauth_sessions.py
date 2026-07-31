"""add single-use native OAuth sessions

Revision ID: 0008_mobile_oauth_sessions
Revises: 0007_credit_ledger_immutability
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_mobile_oauth_sessions"
down_revision = "0007_credit_ledger_immutability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mobile_oauth_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("client_state", sa.String(), nullable=False),
        sa.Column("client_nonce", sa.String(), nullable=False),
        sa.Column("provider_nonce", sa.String(), nullable=False),
        sa.Column("provider_code_verifier", sa.String(), nullable=False),
        sa.Column("code_challenge", sa.String(), nullable=False),
        sa.Column("redirect_uri", sa.String(), nullable=False),
        sa.Column("exchange_code_hash", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state"),
        sa.UniqueConstraint("exchange_code_hash"),
    )
    for column in ("provider", "state", "exchange_code_hash", "user_id", "expires_at"):
        op.create_index(f"ix_mobile_oauth_sessions_{column}", "mobile_oauth_sessions", [column], unique=column in {"state", "exchange_code_hash"})


def downgrade() -> None:
    op.drop_table("mobile_oauth_sessions")
