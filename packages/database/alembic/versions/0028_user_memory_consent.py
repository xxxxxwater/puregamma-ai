"""add user memory consent timestamp

Revision ID: 0028_user_memory_consent
Revises: 0027_user_membership_tier
"""

from alembic import op
import sqlalchemy as sa


revision = "0028_user_memory_consent"
down_revision = "0027_user_membership_tier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent for the same reason as 0027: local/dev schemas created with
    # create_all may already carry the column.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns("users")}
    if "memory_consent_granted_at" not in existing:
        op.add_column(
            "users",
            sa.Column("memory_consent_granted_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("users", "memory_consent_granted_at")
