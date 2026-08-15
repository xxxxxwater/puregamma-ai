"""add user membership tier (bronze/silver/gold)

Revision ID: 0027_user_membership_tier
Revises: 0026_live_trading_control_plane
"""

from alembic import op
import sqlalchemy as sa


revision = "0027_user_membership_tier"
down_revision = "0026_live_trading_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: local/dev schemas created with create_all already contain
    # the column; skipping existing columns keeps fresh installs and existing
    # databases aligned without PostgreSQL-only "ADD COLUMN IF NOT EXISTS"
    # syntax that SQLite rejects.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns("users")}
    if "membership_tier" not in existing:
        op.add_column(
            "users",
            sa.Column("membership_tier", sa.String(), nullable=False, server_default="silver"),
        )
    existing_indexes = {index["name"] for index in inspector.get_indexes("users")}
    if "ix_users_membership_tier" not in existing_indexes:
        op.create_index(
            op.f("ix_users_membership_tier"), "users", ["membership_tier"], unique=False
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_users_membership_tier"), table_name="users")
    op.drop_column("users", "membership_tier")
