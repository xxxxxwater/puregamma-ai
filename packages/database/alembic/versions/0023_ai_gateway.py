"""add the first-party AI gateway domain

Revision ID: 0023_ai_gateway
Revises: 0022_research_run_billing
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_ai_gateway"
down_revision = "0022_research_run_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gateway_providers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("base_url", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("health_status", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("last_health_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_gateway_providers_name", "gateway_providers", ["name"])
    op.create_index("ix_gateway_providers_enabled", "gateway_providers", ["enabled"])
    op.create_index("ix_gateway_providers_health_status", "gateway_providers", ["health_status"])

    op.create_table(
        "gateway_models",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("public_id", sa.String(), nullable=False),
        sa.Column("provider_id", sa.String(), nullable=False),
        sa.Column("provider_model_id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("routing", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("active_pricing_id", sa.String(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["gateway_providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    for name, columns in (
        ("ix_gateway_models_public_id", ["public_id"]),
        ("ix_gateway_models_provider_id", ["provider_id"]),
        ("ix_gateway_models_status", ["status"]),
        ("ix_gateway_models_active_pricing_id", ["active_pricing_id"]),
    ):
        op.create_index(name, "gateway_models", columns)

    op.create_table(
        "gateway_pricing_policies",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False, server_default="default"),
        sa.Column("markup_bps", sa.Integer(), nullable=False, server_default="3000"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by_user_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_gateway_pricing_policies_active", "gateway_pricing_policies", ["active"])

    op.create_table(
        "gateway_price_revisions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("currency", sa.String(), nullable=False, server_default="USD"),
        sa.Column("markup_bps", sa.Integer(), nullable=False, server_default="3000"),
        sa.Column("official_prices", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("final_prices", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_type", sa.String(), nullable=False, server_default="config"),
        sa.Column("source_reference", sa.String(), nullable=True),
        sa.Column("source_hash", sa.String(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_id", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["model_id"], ["gateway_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_gateway_price_revisions_model_id", ["model_id"]),
        ("ix_gateway_price_revisions_status", ["status"]),
        ("ix_gateway_price_revisions_source_hash", ["source_hash"]),
    ):
        op.create_index(name, "gateway_price_revisions", columns)

    op.create_table(
        "gateway_accounts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("monthly_spend_limit_usd", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("current_month_spend_usd", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("current_month_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_gateway_accounts_user_id", "gateway_accounts", ["user_id"])
    op.create_index("ix_gateway_accounts_status", "gateway_accounts", ["status"])

    op.create_table(
        "gateway_api_keys",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("key_hint", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("last_four", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("rate_limit_rpm", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default='["chat"]'),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_from_key_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rotated_from_key_id"], ["gateway_api_keys.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    for name, columns in (
        ("ix_gateway_api_keys_user_id", ["user_id"]),
        ("ix_gateway_api_keys_key_hint", ["key_hint"]),
        ("ix_gateway_api_keys_key_hash", ["key_hash"]),
        ("ix_gateway_api_keys_status", ["status"]),
    ):
        op.create_index(name, "gateway_api_keys", columns)

    op.create_table(
        "gateway_request_logs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("api_key_id", sa.String(), nullable=True),
        sa.Column("provider_id", sa.String(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("public_model", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("long_context_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("image_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("audio_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("search_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("upload_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("download_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("batch_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_cost_usd", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("retail_cost_usd", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["api_key_id"], ["gateway_api_keys.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["model_id"], ["gateway_models.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["provider_id"], ["gateway_providers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    for name, columns in (
        ("ix_gateway_request_logs_request_id", ["request_id"]),
        ("ix_gateway_request_logs_user_id", ["user_id"]),
        ("ix_gateway_request_logs_api_key_id", ["api_key_id"]),
        ("ix_gateway_request_logs_provider_id", ["provider_id"]),
        ("ix_gateway_request_logs_model_id", ["model_id"]),
        ("ix_gateway_request_logs_public_model", ["public_model"]),
        ("ix_gateway_request_logs_status", ["status"]),
        ("ix_gateway_request_logs_ip_address", ["ip_address"]),
        ("ix_gateway_request_logs_error_code", ["error_code"]),
        ("ix_gateway_request_logs_created_at", ["created_at"]),
    ):
        op.create_index(name, "gateway_request_logs", columns)

    op.create_table(
        "gateway_provider_syncs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("provider_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending_review"),
        sa.Column("triggered_by", sa.String(), nullable=False, server_default="scheduler"),
        sa.Column("triggered_by_user_id", sa.String(), nullable=True),
        sa.Column("models_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prices_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["provider_id"], ["gateway_providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_gateway_provider_syncs_provider_id", ["provider_id"]),
        ("ix_gateway_provider_syncs_status", ["status"]),
    ):
        op.create_index(name, "gateway_provider_syncs", columns)

    op.create_table(
        "gateway_ip_blocks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("ip_address", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("created_by_user_id", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ip_address"),
    )
    for name, columns in (
        ("ix_gateway_ip_blocks_ip_address", ["ip_address"]),
        ("ix_gateway_ip_blocks_active", ["active"]),
        ("ix_gateway_ip_blocks_expires_at", ["expires_at"]),
    ):
        op.create_index(name, "gateway_ip_blocks", columns)

    op.create_table(
        "gateway_security_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("api_key_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False, server_default="warning"),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["api_key_id"], ["gateway_api_keys.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_gateway_security_events_user_id", ["user_id"]),
        ("ix_gateway_security_events_api_key_id", ["api_key_id"]),
        ("ix_gateway_security_events_event_type", ["event_type"]),
        ("ix_gateway_security_events_severity", ["severity"]),
        ("ix_gateway_security_events_ip_address", ["ip_address"]),
        ("ix_gateway_security_events_created_at", ["created_at"]),
    ):
        op.create_index(name, "gateway_security_events", columns)


def downgrade() -> None:
    for table, indexes in (
        ("gateway_security_events", ("ix_gateway_security_events_created_at", "ix_gateway_security_events_ip_address", "ix_gateway_security_events_severity", "ix_gateway_security_events_event_type", "ix_gateway_security_events_api_key_id", "ix_gateway_security_events_user_id")),
        ("gateway_ip_blocks", ("ix_gateway_ip_blocks_expires_at", "ix_gateway_ip_blocks_active", "ix_gateway_ip_blocks_ip_address")),
        ("gateway_provider_syncs", ("ix_gateway_provider_syncs_status", "ix_gateway_provider_syncs_provider_id")),
        ("gateway_request_logs", ("ix_gateway_request_logs_created_at", "ix_gateway_request_logs_error_code", "ix_gateway_request_logs_ip_address", "ix_gateway_request_logs_status", "ix_gateway_request_logs_public_model", "ix_gateway_request_logs_model_id", "ix_gateway_request_logs_provider_id", "ix_gateway_request_logs_api_key_id", "ix_gateway_request_logs_user_id", "ix_gateway_request_logs_request_id")),
        ("gateway_api_keys", ("ix_gateway_api_keys_status", "ix_gateway_api_keys_key_hash", "ix_gateway_api_keys_key_hint", "ix_gateway_api_keys_user_id")),
        ("gateway_accounts", ("ix_gateway_accounts_status", "ix_gateway_accounts_user_id")),
        ("gateway_price_revisions", ("ix_gateway_price_revisions_source_hash", "ix_gateway_price_revisions_status", "ix_gateway_price_revisions_model_id")),
        ("gateway_pricing_policies", ("ix_gateway_pricing_policies_active",)),
        ("gateway_models", ("ix_gateway_models_active_pricing_id", "ix_gateway_models_status", "ix_gateway_models_provider_id", "ix_gateway_models_public_id")),
        ("gateway_providers", ("ix_gateway_providers_health_status", "ix_gateway_providers_enabled", "ix_gateway_providers_name")),
    ):
        for index in indexes:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
