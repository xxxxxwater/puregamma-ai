"""align harness research model defaults with DeepSeek V4.1 Flash

DeepSeek released V4.1 Flash on 2026-09-10 under the official API model name
``deepseek-flash``. The previous ``deepseek-v4-flash`` name still resolves to
the same model but must no longer be a default for new rows.

This migration only changes the *default* of
``harness_research_runs.model``. It deliberately does not touch existing rows:
the model that actually served a historical run stays recorded as-is, so the
audit trail remains truthful. New runs get their model from application
configuration (see ``Settings.harness_effective_model``); this server default
is the fallback for any insert path that omits the column.

Revision ID: 0031_deepseek_v41_flash_defaults
Revises: 0030_x_inbound_tasks
Create Date: 2026-09-11
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0031_deepseek_v41_flash_defaults"
down_revision = "0030_x_inbound_tasks"
branch_labels = None
depends_on = None

TABLE = "harness_research_runs"
COLUMN = "model"
NEW_DEFAULT = "deepseek-flash"
OLD_DEFAULT = "deepseek-v4-flash"


def _set_default(value: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            TABLE,
            COLUMN,
            existing_type=sa.String(),
            existing_nullable=False,
            server_default=sa.text(f"'{value}'"),
        )
        return
    # SQLite cannot ALTER a column default in place. The column keeps its
    # Python-side default from the ORM, and the model is always written
    # explicitly by the service layer, so there is nothing unsafe to change
    # here for local/test databases.
    return


def upgrade() -> None:
    _set_default(NEW_DEFAULT)


def downgrade() -> None:
    _set_default(OLD_DEFAULT)
