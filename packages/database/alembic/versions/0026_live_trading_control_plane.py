"""live trading control plane foundation

Additive migration for the LIVE Trading Control Plane. Creates broker
connections, LIVE user approvals, kill switches, market price snapshots,
LIVE order intents, risk checks, LIVE orders, fills, the immutable ledger,
server-side NAV snapshots, and trading reconciliations. The existing
``trading_mandates`` table is extended (renamed risk columns plus new
environment/status/approved_by/broker_connection_id columns) and
``trading_audit_logs`` gains an optional trace_id.

No existing PAPER/SHADOW table is altered in a breaking way. LIVE stays
disabled until every feature flag and approval gate passes (see
docs/live-trading/FEATURE_FLAGS.md).

Revision ID: 0026_live_trading_control_plane
Revises: 0025_harness_research
"""

from alembic import op
import sqlalchemy as sa


revision = "0026_live_trading_control_plane"
down_revision = "0025_harness_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- broker connections (secrets stay encrypted/out-of-band) -----------
    op.create_table(
        "broker_connections",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("account_label", sa.String(), nullable=False),
        sa.Column("encrypted_credentials_ref", sa.Text(), nullable=True),
        sa.Column("permissions_json", sa.JSON(), nullable=False),
        sa.Column("environment", sa.String(), nullable=False, server_default="paper"),
        sa.Column("status", sa.String(), nullable=False, server_default="DISCONNECTED"),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "provider", "account_label", name="uq_broker_connection_label"
        ),
    )
    op.create_index("ix_broker_connections_user_id", "broker_connections", ["user_id"], unique=False)
    op.create_index("ix_broker_connections_provider", "broker_connections", ["provider"], unique=False)
    op.create_index("ix_broker_connections_environment", "broker_connections", ["environment"], unique=False)
    op.create_index("ix_broker_connections_status", "broker_connections", ["status"], unique=False)

    # --- extend trading_mandates (rename + new columns) ---------------------
    op.alter_column(
        "trading_mandates", "asset_allowlist_json", new_column_name="allowed_symbols_json"
    )
    op.alter_column(
        "trading_mandates", "approval_state", new_column_name="approval_status"
    )
    op.add_column(
        "trading_mandates",
        sa.Column("environment", sa.String(), nullable=False, server_default="paper"),
    )
    op.add_column(
        "trading_mandates",
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
    )
    op.add_column("trading_mandates", sa.Column("approved_by", sa.String(), nullable=True))
    op.add_column(
        "trading_mandates", sa.Column("broker_connection_id", sa.String(), nullable=True)
    )
    op.create_index("ix_trading_mandates_environment", "trading_mandates", ["environment"], unique=False)
    op.create_index("ix_trading_mandates_status", "trading_mandates", ["status"], unique=False)
    op.create_index(
        "ix_trading_mandates_broker_connection_id",
        "trading_mandates",
        ["broker_connection_id"],
        unique=False,
    )
    # SQLite cannot ALTER ADD CONSTRAINT; the ORM-level FK strings still apply
    # and PostgreSQL gets real constraints.
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_trading_mandates_approved_by",
            "trading_mandates",
            "users",
            ["approved_by"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_foreign_key(
            "fk_trading_mandates_broker_connection",
            "trading_mandates",
            "broker_connections",
            ["broker_connection_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # --- trace_id on the shared trading audit log ---------------------------
    op.add_column("trading_audit_logs", sa.Column("trace_id", sa.String(), nullable=True))
    op.create_index("ix_trading_audit_logs_trace_id", "trading_audit_logs", ["trace_id"], unique=False)

    # --- LIVE user approvals ------------------------------------------------
    op.create_table(
        "live_user_approvals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("max_total_notional", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_live_user_approvals_user_id", "live_user_approvals", ["user_id"], unique=True)
    op.create_index("ix_live_user_approvals_status", "live_user_approvals", ["status"], unique=False)

    # --- kill switches -------------------------------------------------------
    op.create_table(
        "trading_kill_switches",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=True),
        sa.Column("state", sa.String(), nullable=False, server_default="active"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("triggered_by", sa.String(), nullable=False, server_default="admin"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trading_kill_switches_scope", "trading_kill_switches", ["scope"], unique=False)
    op.create_index("ix_trading_kill_switches_scope_id", "trading_kill_switches", ["scope_id"], unique=False)
    op.create_index("ix_trading_kill_switches_state", "trading_kill_switches", ["state"], unique=False)
    op.create_index("ix_trading_kill_switches_triggered_by", "trading_kill_switches", ["triggered_by"], unique=False)
    op.create_index("ix_trading_kill_switches_trace_id", "trading_kill_switches", ["trace_id"], unique=False)

    # --- market price snapshots ---------------------------------------------
    op.create_table(
        "market_price_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("venue", sa.String(), nullable=False, server_default="MOCK"),
        sa.Column("price", sa.Numeric(20, 8), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="runtime"),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_price_snapshots_symbol", "market_price_snapshots", ["symbol"], unique=False)
    op.create_index("ix_market_price_snapshots_captured_at", "market_price_snapshots", ["captured_at"], unique=False)
    op.create_index(
        "ix_market_price_lookup", "market_price_snapshots", ["symbol", "venue", "captured_at"], unique=False
    )

    # --- LIVE order intents --------------------------------------------------
    op.create_table(
        "live_order_intents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("mandate_id", sa.String(), nullable=False),
        sa.Column("strategy_release_id", sa.String(), nullable=True),
        sa.Column("broker_connection_id", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("side", sa.String(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("order_type", sa.String(), nullable=False, server_default="market"),
        sa.Column("limit_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("client_order_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="user_confirmed"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("confirmation_token_hash", sa.String(), nullable=True),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["broker_connection_id"], ["broker_connections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["mandate_id"], ["trading_mandates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["strategy_release_id"], ["strategy_releases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_live_order_intent_idempotency"),
    )
    op.create_index("ix_live_order_intents_user_id", "live_order_intents", ["user_id"], unique=False)
    op.create_index("ix_live_order_intents_mandate_id", "live_order_intents", ["mandate_id"], unique=False)
    op.create_index("ix_live_order_intents_strategy_release_id", "live_order_intents", ["strategy_release_id"], unique=False)
    op.create_index("ix_live_order_intents_symbol", "live_order_intents", ["symbol"], unique=False)
    op.create_index("ix_live_order_intents_side", "live_order_intents", ["side"], unique=False)
    op.create_index("ix_live_order_intents_client_order_id", "live_order_intents", ["client_order_id"], unique=False)
    op.create_index("ix_live_order_intents_source", "live_order_intents", ["source"], unique=False)
    op.create_index("ix_live_order_intents_expires_at", "live_order_intents", ["expires_at"], unique=False)
    op.create_index("ix_live_order_intents_status", "live_order_intents", ["status"], unique=False)
    op.create_index("ix_live_order_intents_trace_id", "live_order_intents", ["trace_id"], unique=False)

    # --- risk checks ----------------------------------------------------------
    op.create_table(
        "risk_checks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("order_intent_id", sa.String(), nullable=False),
        sa.Column("mandate_id", sa.String(), nullable=False),
        sa.Column("result", sa.String(), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("checks_json", sa.JSON(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_engine_version", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["mandate_id"], ["trading_mandates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_intent_id"], ["live_order_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_risk_checks_user_id", "risk_checks", ["user_id"], unique=False)
    op.create_index("ix_risk_checks_order_intent_id", "risk_checks", ["order_intent_id"], unique=False)
    op.create_index("ix_risk_checks_mandate_id", "risk_checks", ["mandate_id"], unique=False)
    op.create_index("ix_risk_checks_result", "risk_checks", ["result"], unique=False)
    op.create_index("ix_risk_checks_risk_engine_version", "risk_checks", ["risk_engine_version"], unique=False)
    op.create_index("ix_risk_checks_trace_id", "risk_checks", ["trace_id"], unique=False)

    # --- LIVE orders ----------------------------------------------------------
    op.create_table(
        "live_orders",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("mandate_id", sa.String(), nullable=False),
        sa.Column("order_intent_id", sa.String(), nullable=False),
        sa.Column("broker_connection_id", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("side", sa.String(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("order_type", sa.String(), nullable=False, server_default="market"),
        sa.Column("limit_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("client_order_id", sa.String(), nullable=False),
        sa.Column("broker_order_id", sa.String(), nullable=True),
        sa.Column("filled_quantity", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("average_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_ack_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["broker_connection_id"], ["broker_connections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["mandate_id"], ["trading_mandates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_intent_id"], ["live_order_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_live_order_idempotency"),
    )
    op.create_index("ix_live_orders_user_id", "live_orders", ["user_id"], unique=False)
    op.create_index("ix_live_orders_mandate_id", "live_orders", ["mandate_id"], unique=False)
    op.create_index("ix_live_orders_order_intent_id", "live_orders", ["order_intent_id"], unique=False)
    op.create_index("ix_live_orders_symbol", "live_orders", ["symbol"], unique=False)
    op.create_index("ix_live_orders_side", "live_orders", ["side"], unique=False)
    op.create_index("ix_live_orders_status", "live_orders", ["status"], unique=False)
    op.create_index("ix_live_orders_client_order_id", "live_orders", ["client_order_id"], unique=False)
    op.create_index("ix_live_orders_broker_order_id", "live_orders", ["broker_order_id"], unique=False)
    op.create_index("ix_live_orders_trace_id", "live_orders", ["trace_id"], unique=False)

    # --- fills -----------------------------------------------------------------
    op.create_table(
        "fills",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("order_id", sa.String(), nullable=False),
        sa.Column("mandate_id", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("side", sa.String(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=False),
        sa.Column("fee", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("fee_currency", sa.String(), nullable=False, server_default="USD"),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("broker_fill_id", sa.String(), nullable=False),
        sa.Column("raw_reference_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["mandate_id"], ["trading_mandates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["live_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("broker_fill_id", name="uq_fill_broker_fill_id"),
    )
    op.create_index("ix_fills_user_id", "fills", ["user_id"], unique=False)
    op.create_index("ix_fills_order_id", "fills", ["order_id"], unique=False)
    op.create_index("ix_fills_mandate_id", "fills", ["mandate_id"], unique=False)
    op.create_index("ix_fills_symbol", "fills", ["symbol"], unique=False)
    op.create_index("ix_fills_side", "fills", ["side"], unique=False)
    op.create_index("ix_fills_executed_at", "fills", ["executed_at"], unique=False)

    # --- immutable ledger -------------------------------------------------------
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("mandate_id", sa.String(), nullable=True),
        sa.Column("entry_type", sa.String(), nullable=False),
        sa.Column("ref_type", sa.String(), nullable=True),
        sa.Column("ref_id", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=True),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=True),
        sa.Column("price", sa.Numeric(20, 8), nullable=True),
        sa.Column("amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("currency", sa.String(), nullable=False, server_default="USD"),
        sa.Column("balance_after", sa.Numeric(20, 8), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["trading_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mandate_id"], ["trading_mandates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_ledger_entry_idempotency"),
    )
    op.create_index("ix_ledger_entries_user_id", "ledger_entries", ["user_id"], unique=False)
    op.create_index("ix_ledger_entries_account_id", "ledger_entries", ["account_id"], unique=False)
    op.create_index("ix_ledger_entries_mandate_id", "ledger_entries", ["mandate_id"], unique=False)
    op.create_index("ix_ledger_entries_entry_type", "ledger_entries", ["entry_type"], unique=False)
    op.create_index("ix_ledger_entries_ref_id", "ledger_entries", ["ref_id"], unique=False)
    op.create_index("ix_ledger_entries_trace_id", "ledger_entries", ["trace_id"], unique=False)
    op.create_index("ix_ledger_entries_created_at", "ledger_entries", ["created_at"], unique=False)
    op.create_index(
        "ix_ledger_entries_account_created", "ledger_entries", ["account_id", "created_at"], unique=False
    )

    # --- NAV snapshots -----------------------------------------------------------
    op.create_table(
        "nav_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("mandate_id", sa.String(), nullable=True),
        sa.Column("nav", sa.Numeric(20, 8), nullable=True),
        sa.Column("cash", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("gross_exposure", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("net_exposure", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("realized_pnl", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("unrealized_pnl", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(), nullable=False, server_default="USD"),
        sa.Column("price_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("calculation_version", sa.String(), nullable=False, server_default="1.0.0"),
        sa.Column("reconciliation_status", sa.String(), nullable=False, server_default="pending"),
        sa.ForeignKeyConstraint(["account_id"], ["trading_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mandate_id"], ["trading_mandates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_nav_snapshots_user_id", "nav_snapshots", ["user_id"], unique=False)
    op.create_index("ix_nav_snapshots_account_id", "nav_snapshots", ["account_id"], unique=False)
    op.create_index("ix_nav_snapshots_mandate_id", "nav_snapshots", ["mandate_id"], unique=False)
    op.create_index("ix_nav_snapshots_calculated_at", "nav_snapshots", ["calculated_at"], unique=False)
    op.create_index("ix_nav_snapshots_is_stale", "nav_snapshots", ["is_stale"], unique=False)
    op.create_index(
        "ix_nav_snapshots_reconciliation_status", "nav_snapshots", ["reconciliation_status"], unique=False
    )
    op.create_index(
        "ix_nav_snapshots_account_calculated", "nav_snapshots", ["account_id", "calculated_at"], unique=False
    )

    # --- trading reconciliations --------------------------------------------------
    op.create_table(
        "trading_reconciliations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("mandate_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="ok"),
        sa.Column("exchange_balance_json", sa.JSON(), nullable=False),
        sa.Column("ledger_balance_json", sa.JSON(), nullable=False),
        sa.Column("nav_json", sa.JSON(), nullable=False),
        sa.Column("differences_json", sa.JSON(), nullable=False),
        sa.Column("actions_json", sa.JSON(), nullable=False),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["trading_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mandate_id"], ["trading_mandates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trading_reconciliations_user_id", "trading_reconciliations", ["user_id"], unique=False)
    op.create_index("ix_trading_reconciliations_account_id", "trading_reconciliations", ["account_id"], unique=False)
    op.create_index("ix_trading_reconciliations_mandate_id", "trading_reconciliations", ["mandate_id"], unique=False)
    op.create_index("ix_trading_reconciliations_status", "trading_reconciliations", ["status"], unique=False)
    op.create_index("ix_trading_reconciliations_trace_id", "trading_reconciliations", ["trace_id"], unique=False)
    op.create_index("ix_trading_reconciliations_created_at", "trading_reconciliations", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_trading_reconciliations_created_at", table_name="trading_reconciliations")
    op.drop_index("ix_trading_reconciliations_trace_id", table_name="trading_reconciliations")
    op.drop_index("ix_trading_reconciliations_status", table_name="trading_reconciliations")
    op.drop_index("ix_trading_reconciliations_mandate_id", table_name="trading_reconciliations")
    op.drop_index("ix_trading_reconciliations_account_id", table_name="trading_reconciliations")
    op.drop_index("ix_trading_reconciliations_user_id", table_name="trading_reconciliations")
    op.drop_table("trading_reconciliations")

    op.drop_index("ix_nav_snapshots_account_calculated", table_name="nav_snapshots")
    op.drop_index("ix_nav_snapshots_reconciliation_status", table_name="nav_snapshots")
    op.drop_index("ix_nav_snapshots_is_stale", table_name="nav_snapshots")
    op.drop_index("ix_nav_snapshots_calculated_at", table_name="nav_snapshots")
    op.drop_index("ix_nav_snapshots_mandate_id", table_name="nav_snapshots")
    op.drop_index("ix_nav_snapshots_account_id", table_name="nav_snapshots")
    op.drop_index("ix_nav_snapshots_user_id", table_name="nav_snapshots")
    op.drop_table("nav_snapshots")

    op.drop_index("ix_ledger_entries_account_created", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_created_at", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_trace_id", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_ref_id", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_entry_type", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_mandate_id", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_account_id", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_user_id", table_name="ledger_entries")
    op.drop_table("ledger_entries")

    op.drop_index("ix_fills_executed_at", table_name="fills")
    op.drop_index("ix_fills_side", table_name="fills")
    op.drop_index("ix_fills_symbol", table_name="fills")
    op.drop_index("ix_fills_mandate_id", table_name="fills")
    op.drop_index("ix_fills_order_id", table_name="fills")
    op.drop_index("ix_fills_user_id", table_name="fills")
    op.drop_table("fills")

    op.drop_index("ix_live_orders_trace_id", table_name="live_orders")
    op.drop_index("ix_live_orders_broker_order_id", table_name="live_orders")
    op.drop_index("ix_live_orders_client_order_id", table_name="live_orders")
    op.drop_index("ix_live_orders_status", table_name="live_orders")
    op.drop_index("ix_live_orders_side", table_name="live_orders")
    op.drop_index("ix_live_orders_symbol", table_name="live_orders")
    op.drop_index("ix_live_orders_order_intent_id", table_name="live_orders")
    op.drop_index("ix_live_orders_mandate_id", table_name="live_orders")
    op.drop_index("ix_live_orders_user_id", table_name="live_orders")
    op.drop_table("live_orders")

    op.drop_index("ix_risk_checks_trace_id", table_name="risk_checks")
    op.drop_index("ix_risk_checks_risk_engine_version", table_name="risk_checks")
    op.drop_index("ix_risk_checks_result", table_name="risk_checks")
    op.drop_index("ix_risk_checks_mandate_id", table_name="risk_checks")
    op.drop_index("ix_risk_checks_order_intent_id", table_name="risk_checks")
    op.drop_index("ix_risk_checks_user_id", table_name="risk_checks")
    op.drop_table("risk_checks")

    op.drop_index("ix_live_order_intents_trace_id", table_name="live_order_intents")
    op.drop_index("ix_live_order_intents_status", table_name="live_order_intents")
    op.drop_index("ix_live_order_intents_expires_at", table_name="live_order_intents")
    op.drop_index("ix_live_order_intents_source", table_name="live_order_intents")
    op.drop_index("ix_live_order_intents_client_order_id", table_name="live_order_intents")
    op.drop_index("ix_live_order_intents_side", table_name="live_order_intents")
    op.drop_index("ix_live_order_intents_symbol", table_name="live_order_intents")
    op.drop_index("ix_live_order_intents_strategy_release_id", table_name="live_order_intents")
    op.drop_index("ix_live_order_intents_mandate_id", table_name="live_order_intents")
    op.drop_index("ix_live_order_intents_user_id", table_name="live_order_intents")
    op.drop_table("live_order_intents")

    op.drop_index("ix_market_price_lookup", table_name="market_price_snapshots")
    op.drop_index("ix_market_price_snapshots_captured_at", table_name="market_price_snapshots")
    op.drop_index("ix_market_price_snapshots_symbol", table_name="market_price_snapshots")
    op.drop_table("market_price_snapshots")

    op.drop_index("ix_trading_kill_switches_trace_id", table_name="trading_kill_switches")
    op.drop_index("ix_trading_kill_switches_triggered_by", table_name="trading_kill_switches")
    op.drop_index("ix_trading_kill_switches_state", table_name="trading_kill_switches")
    op.drop_index("ix_trading_kill_switches_scope_id", table_name="trading_kill_switches")
    op.drop_index("ix_trading_kill_switches_scope", table_name="trading_kill_switches")
    op.drop_table("trading_kill_switches")

    op.drop_index("ix_live_user_approvals_status", table_name="live_user_approvals")
    op.drop_index("ix_live_user_approvals_user_id", table_name="live_user_approvals")
    op.drop_table("live_user_approvals")

    op.drop_index("ix_trading_audit_logs_trace_id", table_name="trading_audit_logs")
    op.drop_column("trading_audit_logs", "trace_id")

    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_trading_mandates_broker_connection", "trading_mandates", type_="foreignkey")
        op.drop_constraint("fk_trading_mandates_approved_by", "trading_mandates", type_="foreignkey")
    op.drop_index("ix_trading_mandates_broker_connection_id", table_name="trading_mandates")
    op.drop_index("ix_trading_mandates_status", table_name="trading_mandates")
    op.drop_index("ix_trading_mandates_environment", table_name="trading_mandates")
    op.drop_column("trading_mandates", "broker_connection_id")
    op.drop_column("trading_mandates", "approved_by")
    op.drop_column("trading_mandates", "status")
    op.drop_column("trading_mandates", "environment")
    op.alter_column(
        "trading_mandates", "approval_status", new_column_name="approval_state"
    )
    op.alter_column(
        "trading_mandates", "allowed_symbols_json", new_column_name="asset_allowlist_json"
    )

    op.drop_index("ix_broker_connections_status", table_name="broker_connections")
    op.drop_index("ix_broker_connections_environment", table_name="broker_connections")
    op.drop_index("ix_broker_connections_provider", table_name="broker_connections")
    op.drop_index("ix_broker_connections_user_id", table_name="broker_connections")
    op.drop_table("broker_connections")
