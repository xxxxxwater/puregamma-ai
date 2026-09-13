"""Add tenant attachments, conversation permissions and tool approvals; retain all prior data."""
from alembic import op
import sqlalchemy as sa
revision = "0032_chat_workspace"
down_revision = "0031_deepseek_v41_flash_defaults"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("agent_conversations", sa.Column("permission_mode", sa.String(), server_default="workspace-write", nullable=False))
    op.add_column("agent_tool_calls", sa.Column("approval", sa.String(), nullable=True))
    op.add_column("agent_tool_calls", sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table("agent_attachments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False), sa.Column("mime", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False), sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False), sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_agent_attachments_user_id", "agent_attachments", ["user_id"])

def downgrade():
    # Production rollback keeps additive data; dropping this table would destroy user files.
    raise RuntimeError("Data-preserving migration: roll back application images without dropping attachments.")
