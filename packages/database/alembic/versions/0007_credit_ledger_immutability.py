"""make the credit ledger append-only

Revision ID: 0007_credit_ledger_immutability
Revises: 0006_credit_state_machine
"""
from alembic import op


revision = "0007_credit_ledger_immutability"
down_revision = "0006_credit_state_machine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION puregamma_prevent_credit_ledger_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'credit_ledger is append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER credit_ledger_append_only
            BEFORE UPDATE OR DELETE ON credit_ledger
            FOR EACH ROW EXECUTE FUNCTION puregamma_prevent_credit_ledger_mutation()
            """
        )
    elif dialect == "sqlite":
        op.execute(
            """
            CREATE TRIGGER credit_ledger_no_update
            BEFORE UPDATE ON credit_ledger
            BEGIN
                SELECT RAISE(ABORT, 'credit_ledger is append-only');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER credit_ledger_no_delete
            BEFORE DELETE ON credit_ledger
            BEGIN
                SELECT RAISE(ABORT, 'credit_ledger is append-only');
            END
            """
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS credit_ledger_append_only ON credit_ledger")
        op.execute("DROP FUNCTION IF EXISTS puregamma_prevent_credit_ledger_mutation()")
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS credit_ledger_no_update")
        op.execute("DROP TRIGGER IF EXISTS credit_ledger_no_delete")
