"""daily push preferences and scheduling

Revision ID: 0004_daily_push_preferences
Revises: 0003_portfolio_daily_brief
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_daily_push_preferences"
down_revision = "0003_portfolio_daily_brief"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_brief_preferences",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("timezone", sa.String(), nullable=False, server_default="UTC"),
        sa.Column("local_time", sa.String(), nullable=False, server_default="08:30"),
        sa.Column("channel", sa.String(), nullable=False, server_default="email"),
        sa.Column("locale", sa.String(), nullable=False, server_default="en"),
        sa.Column("include_portfolio", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("include_market", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("include_signals", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("include_risk", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("include_sentiment", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("quiet_hours", sa.JSON(), nullable=False),
        sa.Column("max_length", sa.Integer(), nullable=False, server_default="3000"),
        sa.Column("next_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recipient", sa.String(), nullable=True),
        sa.Column("recipient_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_daily_brief_preferences_enabled", "daily_brief_preferences", ["enabled"])
    op.create_index("ix_daily_brief_preferences_channel", "daily_brief_preferences", ["channel"])
    op.create_index("ix_daily_brief_preferences_next_delivery_at", "daily_brief_preferences", ["next_delivery_at"])


def downgrade() -> None:
    op.drop_index("ix_daily_brief_preferences_next_delivery_at", table_name="daily_brief_preferences")
    op.drop_index("ix_daily_brief_preferences_channel", table_name="daily_brief_preferences")
    op.drop_index("ix_daily_brief_preferences_enabled", table_name="daily_brief_preferences")
    op.drop_table("daily_brief_preferences")
