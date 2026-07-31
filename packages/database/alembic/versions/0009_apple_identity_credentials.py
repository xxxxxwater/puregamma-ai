"""add encrypted identity credential storage

Revision ID: 0009_apple_identity_credentials
Revises: 0008_mobile_oauth_sessions
"""
from alembic import op
import sqlalchemy as sa


revision = "0009_apple_identity_credentials"
down_revision = "0008_mobile_oauth_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_identities", sa.Column("credential_ciphertext", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_identities", "credential_ciphertext")
