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
    # revision existed; skipping existing columns keeps fresh installs and
    # production aligned without PostgreSQL-only "ADD COLUMN IF NOT EXISTS"
    # syntax that SQLite rejects.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns("users")}
    additions = (
        ("password_hash", sa.String()),
        ("email_verification_token", sa.String()),
        ("email_verification_token_expires_at", sa.DateTime(timezone=True)),
        ("password_reset_token", sa.String()),
        ("password_reset_token_expires_at", sa.DateTime(timezone=True)),
    )
    for name, column_type in additions:
        if name not in existing:
            op.add_column("users", sa.Column(name, column_type))
    existing_indexes = {index["name"] for index in inspector.get_indexes("users")}
    if "ix_users_email_verification_token" not in existing_indexes:
        op.create_index("ix_users_email_verification_token", "users", ["email_verification_token"], unique=True)
    if "ix_users_password_reset_token" not in existing_indexes:
        op.create_index("ix_users_password_reset_token", "users", ["password_reset_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_password_reset_token", table_name="users")
    op.drop_index("ix_users_email_verification_token", table_name="users")
    op.drop_column("users", "password_reset_token_expires_at")
    op.drop_column("users", "password_reset_token")
    op.drop_column("users", "email_verification_token_expires_at")
    op.drop_column("users", "email_verification_token")
    op.drop_column("users", "password_hash")
