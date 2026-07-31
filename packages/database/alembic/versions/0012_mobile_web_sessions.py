"""Add one-time mobile-to-web session handoffs.

Revision ID: 0012_mobile_web_sessions
Revises: 0011_skills_library
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_mobile_web_sessions"
down_revision = "0011_skills_library"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mobile_web_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("locale", sa.String(), nullable=False, server_default="en"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mobile_web_sessions_code_hash", "mobile_web_sessions", ["code_hash"], unique=True)
    op.create_index("ix_mobile_web_sessions_user_id", "mobile_web_sessions", ["user_id"])
    op.create_index("ix_mobile_web_sessions_expires_at", "mobile_web_sessions", ["expires_at"])
    op.create_index("ix_mobile_web_sessions_consumed_at", "mobile_web_sessions", ["consumed_at"])


def downgrade() -> None:
    op.drop_index("ix_mobile_web_sessions_consumed_at", table_name="mobile_web_sessions")
    op.drop_index("ix_mobile_web_sessions_expires_at", table_name="mobile_web_sessions")
    op.drop_index("ix_mobile_web_sessions_user_id", table_name="mobile_web_sessions")
    op.drop_index("ix_mobile_web_sessions_code_hash", table_name="mobile_web_sessions")
    op.drop_table("mobile_web_sessions")
