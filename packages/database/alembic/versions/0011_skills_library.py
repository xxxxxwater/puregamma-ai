"""add versioned declarative Skills library

Revision ID: 0011_skills_library
Revises: 0010_push_devices
"""
from alembic import op
import sqlalchemy as sa


revision = "0011_skills_library"
down_revision = "0010_push_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("publisher_name", sa.String(), nullable=False),
        sa.Column("owner_user_id", sa.String(), nullable=True),
        sa.Column("workspace_id", sa.String(), nullable=True),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("current_version", sa.String(), nullable=False),
        sa.Column("asset_classes_json", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(), nullable=False),
        sa.Column("billing_type", sa.String(), nullable=False),
        sa.Column("allow_autopilot", sa.Boolean(), nullable=False),
        sa.Column("allow_order_intent", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_skills_slug"),
        sa.UniqueConstraint("scope", "owner_user_id", "workspace_id", "slug", name="uq_skill_scope_owner_slug"),
    )
    for column in ("slug", "owner_user_id", "workspace_id", "scope", "status"):
        op.create_index(f"ix_skills_{column}", "skills", [column])

    op.create_table(
        "skill_versions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("skill_id", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("content_bundle_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("release_status", sa.String(), nullable=False),
        sa.Column("changelog", sa.Text(), nullable=False),
        sa.Column("validation_json", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_id", "version", name="uq_skill_version"),
    )
    for column in ("skill_id", "content_hash", "release_status"):
        op.create_index(f"ix_skill_versions_{column}", "skill_versions", [column])

    op.create_table(
        "skill_installations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("skill_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("workspace_id", sa.String(), nullable=True),
        sa.Column("installed_by_user_id", sa.String(), nullable=True),
        sa.Column("target_key", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("pinned_version", sa.String(), nullable=True),
        sa.Column("config_overrides_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["installed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_id", "target_key", name="uq_skill_installation_target"),
    )
    for column in ("skill_id", "user_id", "workspace_id", "target_key", "enabled"):
        op.create_index(f"ix_skill_installations_{column}", "skill_installations", [column])

    op.create_table(
        "skill_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("skill_id", sa.String(), nullable=False),
        sa.Column("skill_version_id", sa.String(), nullable=False),
        sa.Column("installation_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=True),
        sa.Column("agent_run_id", sa.String(), nullable=True),
        sa.Column("external_run_id", sa.String(), nullable=True),
        sa.Column("trigger_source", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_summary_json", sa.JSON(), nullable=False),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("usage_json", sa.JSON(), nullable=False),
        sa.Column("credits_reserved", sa.Integer(), nullable=False),
        sa.Column("credits_used", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_version_id"], ["skill_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["installation_id"], ["skill_installations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_skill_run_idempotency"),
    )
    for column in ("skill_id", "skill_version_id", "user_id", "workspace_id", "agent_run_id", "external_run_id", "trigger_source", "status", "trace_id", "started_at"):
        op.create_index(f"ix_skill_runs_{column}", "skill_runs", [column])

    op.create_table(
        "skill_permissions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("skill_id", sa.String(), nullable=False),
        sa.Column("skill_version_id", sa.String(), nullable=False),
        sa.Column("permission_type", sa.String(), nullable=False),
        sa.Column("resource", sa.String(), nullable=False),
        sa.Column("effect", sa.String(), nullable=False),
        sa.Column("constraints_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_version_id"], ["skill_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_version_id", "permission_type", "resource", "effect", name="uq_skill_version_permission"),
    )
    for column in ("skill_id", "skill_version_id", "permission_type"):
        op.create_index(f"ix_skill_permissions_{column}", "skill_permissions", [column])

    op.create_table(
        "skill_sources",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("skill_id", sa.String(), nullable=False),
        sa.Column("skill_version_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("repo_url", sa.Text(), nullable=True),
        sa.Column("commit_hash", sa.String(), nullable=True),
        sa.Column("trust_status", sa.String(), nullable=False),
        sa.Column("imported_by_user_id", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_version_id"], ["skill_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["imported_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("skill_id", "skill_version_id", "source_type", "commit_hash", "trust_status"):
        op.create_index(f"ix_skill_sources_{column}", "skill_sources", [column])


def downgrade() -> None:
    for table in ("skill_sources", "skill_permissions", "skill_runs", "skill_installations", "skill_versions", "skills"):
        op.drop_table(table)
