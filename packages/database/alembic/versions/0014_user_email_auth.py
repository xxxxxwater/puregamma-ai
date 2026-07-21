"""add email auth columns to users table

Revision ID: 0014_user_email_auth
Revises: 0013_imessage_inbound_events
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_user_email_auth"
down_revision = "0013_imessage_inbound_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: production columns were provisioned manually before this
    # revision existed; IF NOT EXISTS keeps fresh installs and production aligned.
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verification_token VARCHAR")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verification_token_expires_at TIMESTAMPTZ")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token VARCHAR")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token_expires_at TIMESTAMPTZ")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_verification_token ON users (email_verification_token)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_password_reset_token ON users (password_reset_token)")


def downgrade() -> None:
    op.drop_index("ix_users_password_reset_token", table_name="users")
    op.drop_index("ix_users_email_verification_token", table_name="users")
    op.drop_column("users", "password_reset_token_expires_at")
    op.drop_column("users", "password_reset_token")
    op.drop_column("users", "email_verification_token_expires_at")
    op.drop_column("users", "email_verification_token")
    op.drop_column("users", "password_hash")
