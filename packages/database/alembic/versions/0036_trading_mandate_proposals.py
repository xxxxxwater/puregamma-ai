"""add trading_mandate_proposals (two-person LIVE mandate approval)

Additive only: one new table, no change to existing tables. The workflow that
uses it is off unless LIVE_MANDATE_PROPOSALS_ENABLED=true; with the flag on and
this migration not yet applied, the API answers 503 instead of failing.

Revision ID: 0036_trading_mandate_proposals
Revises: 0035_repair_legacy_schema
"""

from alembic import op
import sqlalchemy as sa


revision = "0036_trading_mandate_proposals"
down_revision = "0035_repair_legacy_schema"
branch_labels = None
depends_on = None

_INDEXES = (
    ("ix_trading_mandate_proposals_user_id", ["user_id"]),
    ("ix_trading_mandate_proposals_target_mandate_id", ["target_mandate_id"]),
    ("ix_trading_mandate_proposals_proposed_by", ["proposed_by"]),
    ("ix_trading_mandate_proposals_status", ["status"]),
    ("ix_trading_mandate_proposals_expires_at", ["expires_at"]),
    ("ix_trading_mandate_proposals_trace_id", ["trace_id"]),
)


def upgrade() -> None:
    op.create_table(
        "trading_mandate_proposals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False, server_default="create"),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("target_mandate_id", sa.String(), nullable=True),
        sa.Column("base_revision", sa.Integer(), nullable=True),
        sa.Column("proposed_by", sa.String(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("approvals_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_mandate_id", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_mandate_id"], ["trading_mandates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["applied_mandate_id"], ["trading_mandates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_trading_mandate_proposal_idempotency"),
    )
    for name, columns in _INDEXES:
        op.create_index(name, "trading_mandate_proposals", columns)


def downgrade() -> None:
    for name, _ in _INDEXES:
        op.drop_index(name, table_name="trading_mandate_proposals")
    op.drop_table("trading_mandate_proposals")
