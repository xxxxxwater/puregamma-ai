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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns("daily_brief_preferences")}
    additions = (
        ("channels", sa.JSON()),
        ("report_types", sa.JSON()),
        ("failure_count", sa.Integer(), "0"),
        ("last_error", sa.String()),
    )
    for name, column_type, *default in additions:
        if name not in existing:
            op.add_column(
                "daily_brief_preferences",
                sa.Column(name, column_type, server_default=default[0] if default else None),
            )
    # Backfill: existing single channel becomes the channels list. JSON array
    # construction is dialect-specific (json_build_array on PostgreSQL, direct
    # JSON literal on SQLite), so build the value in Python for both.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("UPDATE daily_brief_preferences SET channels = json_build_array(channel) WHERE channels IS NULL AND channel IS NOT NULL")
        op.execute("UPDATE daily_brief_preferences SET channels = json_build_array('email') WHERE channels IS NULL")
    else:
        rows = bind.execute(sa.text("SELECT user_id, channel FROM daily_brief_preferences WHERE channels IS NULL")).fetchall()
        for user_id, channel in rows:
            value = f'["{channel}"]' if channel else '["email"]'
            bind.execute(
                sa.text("UPDATE daily_brief_preferences SET channels = :value WHERE user_id = :user_id"),
                {"value": value, "user_id": user_id},
            )


def downgrade() -> None:
    op.drop_column("daily_brief_preferences", "last_error")
    op.drop_column("daily_brief_preferences", "failure_count")
    op.drop_column("daily_brief_preferences", "report_types")
    op.drop_column("daily_brief_preferences", "channels")
