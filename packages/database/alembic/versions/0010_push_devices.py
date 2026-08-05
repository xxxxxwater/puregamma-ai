"""add encrypted APNs device registrations

Revision ID: 0010_push_devices
Revises: 0009_apple_identity_credentials
"""
from alembic import op
import sqlalchemy as sa


revision = "0010_push_devices"
down_revision = "0009_apple_identity_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_devices",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("token_ciphertext", sa.JSON(), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("environment", sa.String(), nullable=False),
        sa.Column("locale", sa.String(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    for column in ("user_id", "token_hash", "environment", "enabled"):
        op.create_index(f"ix_push_devices_{column}", "push_devices", [column], unique=column == "token_hash")


def downgrade() -> None:
    op.drop_table("push_devices")
