"""iMessage verification and delivery retries

Revision ID: 0005_imessage_delivery_retries
Revises: 0004_daily_push_preferences
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_imessage_delivery_retries"
down_revision = "0004_daily_push_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_preferences") as batch:
        batch.add_column(sa.Column("imessage_recipient_verified_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("notification_deliveries") as batch:
        batch.add_column(sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_error", sa.String(), nullable=True))
        batch.create_index("ix_notification_deliveries_next_retry_at", ["next_retry_at"], unique=False)
    op.create_table(
        "imessage_verification_challenges",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("recipient", sa.String(), nullable=False),
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_imessage_verification_challenges_user_id", "imessage_verification_challenges", ["user_id"])
    op.create_index("ix_imessage_verification_challenges_expires_at", "imessage_verification_challenges", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_imessage_verification_challenges_expires_at", table_name="imessage_verification_challenges")
    op.drop_index("ix_imessage_verification_challenges_user_id", table_name="imessage_verification_challenges")
    op.drop_table("imessage_verification_challenges")
    with op.batch_alter_table("notification_deliveries") as batch:
        batch.drop_index("ix_notification_deliveries_next_retry_at")
        batch.drop_column("last_error")
        batch.drop_column("next_retry_at")
        batch.drop_column("last_attempt_at")
        batch.drop_column("attempt_count")
    with op.batch_alter_table("user_preferences") as batch:
        batch.drop_column("imessage_recipient_verified_at")
