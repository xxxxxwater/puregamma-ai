"""Repair partial legacy databases that were stamped past earlier migrations.

Revision ID: 0035_repair_legacy_schema
Revises: 0034_gateway_wallet_reservations

The repair is additive. A complete database is left unchanged; a partial
database receives the two missing credit tables and Skills columns. Existing
rows are never deleted.
"""

from alembic import op
import sqlalchemy as sa


revision = "0035_repair_legacy_schema"
down_revision = "0034_gateway_wallet_reservations"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    return column in {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def _index_exists(table: str, name: str) -> bool:
    return name in {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}


def _unique_target_exists() -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        tuple(item["column_names"]) == ("skill_id", "target_key")
        for item in inspector.get_unique_constraints("skill_installations")
    ) or any(
        item.get("unique") and tuple(item["column_names"]) == ("skill_id", "target_key")
        for item in inspector.get_indexes("skill_installations")
    )


def upgrade() -> None:
    if not _table_exists("credit_budget_policies"):
        op.create_table(
            "credit_budget_policies",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("automation_key", sa.String(), nullable=False),
            sa.Column("daily_limit", sa.Integer(), nullable=False),
            sa.Column("monthly_limit", sa.Integer(), nullable=False),
            sa.Column("per_run_limit", sa.Integer(), nullable=False),
            sa.Column("alert_threshold_pct", sa.Integer(), nullable=False, server_default="80"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("pause_reason", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "automation_key", name="uq_credit_budget_user_automation"),
        )
        op.create_index("ix_credit_budget_policies_user_id", "credit_budget_policies", ["user_id"])
        op.create_index("ix_credit_budget_policies_automation_key", "credit_budget_policies", ["automation_key"])

    if not _table_exists("credit_reward_grants"):
        op.create_table(
            "credit_reward_grants",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("reward_type", sa.String(), nullable=False),
            sa.Column("credits", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(), nullable=False),
            sa.Column("idempotency_key", sa.String(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("granted_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("ledger_entry_id", sa.String(), sa.ForeignKey("credit_ledger.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("idempotency_key"),
        )
        for column in ("user_id", "reward_type", "created_at"):
            op.create_index(f"ix_credit_reward_grants_{column}", "credit_reward_grants", [column])
        op.create_index("ix_credit_reward_grants_idempotency_key", "credit_reward_grants", ["idempotency_key"], unique=True)

    if _table_exists("skill_installations"):
        if not _column_exists("skill_installations", "target_key"):
            op.add_column("skill_installations", sa.Column("target_key", sa.String(), nullable=True))
            op.execute(
                "UPDATE skill_installations SET target_key = CASE "
                "WHEN workspace_id IS NOT NULL AND workspace_id != '' THEN 'workspace:' || workspace_id "
                "WHEN user_id IS NOT NULL AND user_id != '' THEN 'user:' || user_id "
                "ELSE 'legacy:' || id END"
            )
            with op.batch_alter_table("skill_installations") as batch:
                batch.alter_column("target_key", existing_type=sa.String(), nullable=False)
        if not _index_exists("skill_installations", "ix_skill_installations_target_key"):
            op.create_index("ix_skill_installations_target_key", "skill_installations", ["target_key"])
        if not _unique_target_exists():
            op.create_index("uq_skill_installation_target", "skill_installations", ["skill_id", "target_key"], unique=True)

    if _table_exists("skill_runs"):
        if not _column_exists("skill_runs", "external_run_id"):
            op.add_column("skill_runs", sa.Column("external_run_id", sa.String(), nullable=True))
        if not _index_exists("skill_runs", "ix_skill_runs_external_run_id"):
            op.create_index("ix_skill_runs_external_run_id", "skill_runs", ["external_run_id"])


def downgrade() -> None:
    raise RuntimeError("0035 is an additive repair; restoring the pre-repair snapshot is the rollback")
