"""unified research facts: snapshots, market events, impacts, actions

Revision ID: 0018_research_events
Revises: 0017_plaid_investment_tx
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_research_events"
down_revision = "0017_plaid_investment_tx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_counts_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("health_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(), nullable=False, server_default="completed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_snapshots_kind", "research_snapshots", ["kind"])
    op.create_index("ix_research_snapshots_as_of", "research_snapshots", ["as_of"])
    op.create_index("ix_research_snapshots_status", "research_snapshots", ["status"])

    op.create_table(
        "market_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_provider", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("assets", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("direction", sa.String(), nullable=True),
        sa.Column("time_horizon", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence_gaps", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("research_snapshot_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["research_snapshot_id"], ["research_snapshots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint", name="uq_market_event_fingerprint"),
    )
    op.create_index("ix_market_events_event_type", "market_events", ["event_type"])
    op.create_index("ix_market_events_source_provider", "market_events", ["source_provider"])
    op.create_index("ix_market_events_source_published_at", "market_events", ["source_published_at"])
    op.create_index("ix_market_events_status", "market_events", ["status"])
    op.create_index("ix_market_events_created_at", "market_events", ["created_at"])
    op.create_index("ix_market_events_research_snapshot_id", "market_events", ["research_snapshot_id"])

    op.create_table(
        "asset_impacts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("relation_type", sa.String(), nullable=False, server_default="direct"),
        sa.Column("direction", sa.String(), nullable=True),
        sa.Column("magnitude", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("horizon", sa.String(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["market_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "symbol", "relation_type", name="uq_asset_impact_event_symbol_relation"),
    )
    op.create_index("ix_asset_impacts_event_id", "asset_impacts", ["event_id"])
    op.create_index("ix_asset_impacts_symbol", "asset_impacts", ["symbol"])

    op.create_table(
        "user_portfolio_impacts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("asset_impact_id", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("exposure_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("exposure_weight", sa.Float(), nullable=True),
        sa.Column("direction", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["market_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_impact_id"], ["asset_impacts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "event_id", "symbol", name="uq_user_portfolio_impact"),
    )
    op.create_index("ix_user_portfolio_impacts_user_id", "user_portfolio_impacts", ["user_id"])
    op.create_index("ix_user_portfolio_impacts_event_id", "user_portfolio_impacts", ["event_id"])

    op.create_table(
        "research_actions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("event_id", sa.String(), nullable=True),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("dedup_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["market_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_key", name="uq_research_action_dedup"),
    )
    op.create_index("ix_research_actions_user_id", "research_actions", ["user_id"])
    op.create_index("ix_research_actions_event_id", "research_actions", ["event_id"])
    op.create_index("ix_research_actions_action_type", "research_actions", ["action_type"])
    op.create_index("ix_research_actions_status", "research_actions", ["status"])
    op.create_index("ix_research_actions_created_at", "research_actions", ["created_at"])

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    llm_columns = {column["name"] for column in inspector.get_columns("llm_call_logs")}
    if "latency_ms" not in llm_columns:
        op.add_column("llm_call_logs", sa.Column("latency_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("llm_call_logs", "latency_ms")
    op.drop_table("research_actions")
    op.drop_table("user_portfolio_impacts")
    op.drop_table("asset_impacts")
    op.drop_table("market_events")
    op.drop_table("research_snapshots")
