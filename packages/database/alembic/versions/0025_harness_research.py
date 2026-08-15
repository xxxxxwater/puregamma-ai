"""harness research, memory service, and trading mandate foundations

Additive-only migration. Creates the DeepSeek Harness research tables, the
PureGamma-owned Memory Service tables, and the TradingMandate foundation
(SHADOW/PAPER only; LIVE is never enabled). No existing table is altered.

Revision ID: 0025_harness_research
Revises: 0024_portfolio_nav_snapshots
"""

from alembic import op
import sqlalchemy as sa


revision = "0025_harness_research"
down_revision = "0024_portfolio_nav_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Harness research foundation -------------------------------------
    op.create_table(
        "evidence_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("schema_version", sa.String(), nullable=False, server_default="1.0"),
        sa.Column("source_scope", sa.String(), nullable=False, server_default="run"),
        sa.Column("freshness_window_seconds", sa.Integer(), nullable=False, server_default="900"),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("normalized_evidence_json", sa.JSON(), nullable=False),
        sa.Column("source_ids_json", sa.JSON(), nullable=False),
        sa.Column("provider_list_json", sa.JSON(), nullable=False),
        sa.Column("source_timestamps_json", sa.JSON(), nullable=False),
        sa.Column("fetched_timestamps_json", sa.JSON(), nullable=False),
        sa.Column("mock_fallback_flags_json", sa.JSON(), nullable=False),
        sa.Column("authorization_context_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_snapshots_user_id", "evidence_snapshots", ["user_id"], unique=False)
    op.create_index("ix_evidence_snapshots_content_hash", "evidence_snapshots", ["content_hash"], unique=False)
    op.create_index("ix_evidence_snapshots_source_scope", "evidence_snapshots", ["source_scope"], unique=False)
    # Partial unique indexes: shared (user_id NULL) and user-scoped snapshots
    # are each deduplicated without allowing NULL-key duplicates.
    op.create_index(
        "uq_evidence_snapshot_shared_scope",
        "evidence_snapshots",
        ["content_hash", "source_scope"],
        unique=True,
        sqlite_where=sa.text("user_id IS NULL"),
        postgresql_where=sa.text("user_id IS NULL"),
    )
    op.create_index(
        "uq_evidence_snapshot_user_scope",
        "evidence_snapshots",
        ["content_hash", "source_scope", "user_id"],
        unique=True,
        sqlite_where=sa.text("user_id IS NOT NULL"),
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )

    op.create_table(
        "harness_research_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("parent_agent_run_id", sa.String(), nullable=True),
        sa.Column("skill_run_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("requested_goal_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("input_hash", sa.String(), nullable=False),
        sa.Column("evidence_snapshot_id", sa.String(), nullable=True),
        sa.Column("evidence_snapshot_hash", sa.String(), nullable=True),
        sa.Column("harness_version", sa.String(), nullable=False),
        sa.Column("runtime_version", sa.String(), nullable=False),
        sa.Column("cordis_config_hash", sa.String(), nullable=False),
        sa.Column("plugin_lock_hash", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False, server_default="deepseek"),
        sa.Column("model", sa.String(), nullable=False, server_default="deepseek-v4-flash"),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("queue_task_id", sa.String(), nullable=True),
        sa.Column("queue_priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_budget_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credits_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("usage_json", sa.JSON(), nullable=False),
        sa.Column("artifact_id", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("settlement_status", sa.String(), nullable=True, server_default="none"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["skill_run_id"], ["skill_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["evidence_snapshot_id"], ["evidence_snapshots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_harness_run_idempotency"),
    )
    op.create_index("ix_harness_research_runs_user_id", "harness_research_runs", ["user_id"], unique=False)
    op.create_index("ix_harness_research_runs_status", "harness_research_runs", ["status"], unique=False)
    op.create_index("ix_harness_research_runs_input_hash", "harness_research_runs", ["input_hash"], unique=False)
    op.create_index("ix_harness_research_runs_timeout_at", "harness_research_runs", ["timeout_at"], unique=False)
    op.create_index("ix_harness_research_runs_trace_id", "harness_research_runs", ["trace_id"], unique=False)

    op.create_table(
        "harness_run_state_transitions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("research_run_id", sa.String(), nullable=False),
        sa.Column("from_status", sa.String(), nullable=False),
        sa.Column("to_status", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("actor", sa.String(), nullable=False, server_default="system"),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["research_run_id"], ["harness_research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_harness_run_state_transitions_research_run_id", "harness_run_state_transitions", ["research_run_id"], unique=False)
    op.create_index("ix_harness_run_state_transitions_to_status", "harness_run_state_transitions", ["to_status"], unique=False)
    op.create_index("ix_harness_run_state_transitions_trace_id", "harness_run_state_transitions", ["trace_id"], unique=False)

    op.create_table(
        "research_artifacts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("research_run_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("schema_version", sa.String(), nullable=False, server_default="1.0"),
        sa.Column("structured_json", sa.JSON(), nullable=False),
        sa.Column("markdown_rendering", sa.Text(), nullable=False, server_default=""),
        sa.Column("citations_json", sa.JSON(), nullable=False),
        sa.Column("methodology", sa.Text(), nullable=False, server_default=""),
        sa.Column("assumptions_json", sa.JSON(), nullable=False),
        sa.Column("limitations_json", sa.JSON(), nullable=False),
        sa.Column("tool_run_summaries_json", sa.JSON(), nullable=False),
        sa.Column("artifact_file_refs_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("validation_result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["research_run_id"], ["harness_research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_artifacts_user_id", "research_artifacts", ["user_id"], unique=False)
    op.create_index("ix_research_artifacts_research_run_id", "research_artifacts", ["research_run_id"], unique=False)
    op.create_index("ix_research_artifacts_status", "research_artifacts", ["status"], unique=False)

    op.create_table(
        "strategy_releases",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("strategy_id", sa.String(), nullable=False),
        sa.Column("strategy_version", sa.Integer(), nullable=False),
        sa.Column("release_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("spec_json", sa.JSON(), nullable=False),
        sa.Column("spec_hash", sa.String(), nullable=False),
        sa.Column("review_status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("reviewed_by_user_id", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False, server_default="user"),
        sa.Column("source_artifact_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_artifact_id"], ["research_artifacts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("strategy_id", "strategy_version", "release_number", name="uq_strategy_release_version"),
    )
    op.create_index("ix_strategy_releases_user_id", "strategy_releases", ["user_id"], unique=False)
    op.create_index("ix_strategy_releases_strategy_id", "strategy_releases", ["strategy_id"], unique=False)
    op.create_index("ix_strategy_releases_review_status", "strategy_releases", ["review_status"], unique=False)

    op.create_table(
        "trading_mandates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("strategy_release_id", sa.String(), nullable=False),
        sa.Column("execution_mode", sa.String(), nullable=False, server_default="shadow"),
        sa.Column("asset_allowlist_json", sa.JSON(), nullable=False),
        sa.Column("allowed_side", sa.String(), nullable=False, server_default="both"),
        # Financial risk thresholds use decimal numerics, never float.
        sa.Column("max_total_notional", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("max_per_order_notional", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("max_position_notional", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("max_leverage", sa.Numeric(20, 8), nullable=False, server_default="1"),
        sa.Column("max_daily_loss", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("max_trades_per_day", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_order_frequency_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("allowed_time_windows_json", sa.JSON(), nullable=False),
        sa.Column("data_freshness_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("source_policy_json", sa.JSON(), nullable=False),
        sa.Column("stop_conditions_json", sa.JSON(), nullable=False),
        sa.Column("kill_switch_state", sa.String(), nullable=False, server_default="inactive"),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pause_reason", sa.Text(), nullable=True),
        sa.Column("approval_state", sa.String(), nullable=False, server_default="pending"),
        sa.Column("confirmation_phrase_hash", sa.String(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("audit_metadata_json", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["trading_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["strategy_release_id"], ["strategy_releases.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_trading_mandate_idempotency"),
    )
    op.create_index("ix_trading_mandates_user_id", "trading_mandates", ["user_id"], unique=False)
    op.create_index("ix_trading_mandates_account_id", "trading_mandates", ["account_id"], unique=False)
    op.create_index("ix_trading_mandates_strategy_release_id", "trading_mandates", ["strategy_release_id"], unique=False)
    op.create_index("ix_trading_mandates_execution_mode", "trading_mandates", ["execution_mode"], unique=False)
    op.create_index("ix_trading_mandates_approval_state", "trading_mandates", ["approval_state"], unique=False)

    op.create_table(
        "trading_mandate_audits",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("mandate_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("actor_type", sa.String(), nullable=False, server_default="user"),
        sa.Column("strategy_version", sa.Integer(), nullable=True),
        sa.Column("signal_id", sa.String(), nullable=True),
        sa.Column("runtime_command_id", sa.String(), nullable=True),
        sa.Column("detail_json", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mandate_id"], ["trading_mandates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_mandate_audit_idempotency"),
    )
    op.create_index("ix_trading_mandate_audits_user_id", "trading_mandate_audits", ["user_id"], unique=False)
    op.create_index("ix_trading_mandate_audits_mandate_id", "trading_mandate_audits", ["mandate_id"], unique=False)
    op.create_index("ix_trading_mandate_audits_action", "trading_mandate_audits", ["action"], unique=False)
    op.create_index("ix_trading_mandate_audits_trace_id", "trading_mandate_audits", ["trace_id"], unique=False)

    op.create_table(
        "harness_event_outbox",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_harness_outbox_idempotency"),
    )
    op.create_index("ix_harness_event_outbox_user_id", "harness_event_outbox", ["user_id"], unique=False)
    op.create_index("ix_harness_event_outbox_event_type", "harness_event_outbox", ["event_type"], unique=False)
    op.create_index("ix_harness_event_outbox_status", "harness_event_outbox", ["status"], unique=False)
    op.create_index("ix_harness_event_outbox_trace_id", "harness_event_outbox", ["trace_id"], unique=False)

    # --- Memory Service foundation ---------------------------------------
    op.create_table(
        "conversation_memory_summaries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("summary_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary_token_estimate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recent_message_ids_json", sa.JSON(), nullable=False),
        sa.Column("source_message_ids_json", sa.JSON(), nullable=False),
        sa.Column("goals_json", sa.JSON(), nullable=False),
        sa.Column("known_facts_json", sa.JSON(), nullable=False),
        sa.Column("used_evidence_json", sa.JSON(), nullable=False),
        sa.Column("open_questions_json", sa.JSON(), nullable=False),
        sa.Column("user_preferences_json", sa.JSON(), nullable=False),
        sa.Column("superseded_by", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["agent_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "version", name="uq_conversation_memory_version"),
    )
    op.create_index("ix_conversation_memory_summaries_user_id", "conversation_memory_summaries", ["user_id"], unique=False)
    op.create_index("ix_conversation_memory_summaries_conversation_id", "conversation_memory_summaries", ["conversation_id"], unique=False)

    op.create_table(
        "user_memories",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("source_hash", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("salience", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(), nullable=False, server_default="model_proposed"),
        sa.Column("consent_scope", sa.String(), nullable=False, server_default="none"),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("superseded_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "namespace", "source_hash", name="uq_user_memory_source"),
    )
    op.create_index("ix_user_memories_user_id", "user_memories", ["user_id"], unique=False)
    op.create_index("ix_user_memories_namespace", "user_memories", ["namespace"], unique=False)
    op.create_index("ix_user_memories_kind", "user_memories", ["kind"], unique=False)
    op.create_index("ix_user_memories_status", "user_memories", ["status"], unique=False)
    op.create_index("ix_user_memories_expires_at", "user_memories", ["expires_at"], unique=False)

    op.create_table(
        "memory_scope_settings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("changed_by", sa.String(), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "scope", name="uq_memory_scope_user_scope"),
    )
    op.create_index("ix_memory_scope_settings_user_id", "memory_scope_settings", ["user_id"], unique=False)
    op.create_index("ix_memory_scope_settings_scope", "memory_scope_settings", ["scope"], unique=False)

    op.create_table(
        "memory_proposals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("proposed_by", sa.String(), nullable=False, server_default="model"),
        sa.Column("source_run_id", sa.String(), nullable=True),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False, server_default="model_proposal"),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("source_hash", sa.String(), nullable=False),
        sa.Column("proposed_ttl_seconds", sa.Integer(), nullable=True),
        sa.Column("sensitivity", sa.String(), nullable=False, server_default="low"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decided_by_user_id", sa.String(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("memory_id", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["memory_id"], ["user_memories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_memory_proposal_idempotency"),
    )
    op.create_index("ix_memory_proposals_user_id", "memory_proposals", ["user_id"], unique=False)
    op.create_index("ix_memory_proposals_namespace", "memory_proposals", ["namespace"], unique=False)
    op.create_index("ix_memory_proposals_status", "memory_proposals", ["status"], unique=False)

    op.create_table(
        "memory_audit_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False, server_default="memory"),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("namespace", sa.String(), nullable=True),
        sa.Column("detail_json", sa.JSON(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False, server_default="system"),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_audit_records_user_id", "memory_audit_records", ["user_id"], unique=False)
    op.create_index("ix_memory_audit_records_action", "memory_audit_records", ["action"], unique=False)


def downgrade() -> None:
    op.drop_table("memory_audit_records")
    op.drop_table("memory_proposals")
    op.drop_table("memory_scope_settings")
    op.drop_table("user_memories")
    op.drop_table("conversation_memory_summaries")
    op.drop_table("harness_event_outbox")
    op.drop_table("trading_mandate_audits")
    op.drop_table("trading_mandates")
    op.drop_table("strategy_releases")
    op.drop_table("research_artifacts")
    op.drop_table("harness_run_state_transitions")
    op.drop_table("harness_research_runs")
    op.drop_table("evidence_snapshots")
