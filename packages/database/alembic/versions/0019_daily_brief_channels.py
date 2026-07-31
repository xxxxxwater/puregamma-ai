"""multi-channel daily brief preferences + failure backoff state

Revision ID: 0019_daily_brief_channels
Revises: 0018_research_events
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_daily_brief_channels"
down_revision = "0018_research_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("daily_brief_preferences", sa.Column("channels", sa.JSON(), nullable=True))
    op.add_column("daily_brief_preferences", sa.Column("report_types", sa.JSON(), nullable=True))
    op.add_column("daily_brief_preferences", sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("daily_brief_preferences", sa.Column("last_error", sa.String(), nullable=True))
    # Backfill: existing single channel becomes the channels list.
    op.execute("UPDATE daily_brief_preferences SET channels = json_build_array(channel) WHERE channels IS NULL AND channel IS NOT NULL")
    op.execute("UPDATE daily_brief_preferences SET channels = json_build_array('email') WHERE channels IS NULL")


def downgrade() -> None:
    op.drop_column("daily_brief_preferences", "last_error")
    op.drop_column("daily_brief_preferences", "failure_count")
    op.drop_column("daily_brief_preferences", "report_types")
    op.drop_column("daily_brief_preferences", "channels")
