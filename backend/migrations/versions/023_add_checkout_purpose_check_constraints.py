"""Add CHECK constraints on transactions.purpose and bin_transactions.purpose

Revision ID: 023
Revises: 022
Create Date: 2026-05-20

Changes:
  - Normalize any invalid purpose values to 'GENERAL' on both dialects.
  - PostgreSQL: add real DB CHECK constraints via op.create_check_constraint().
  - SQLite: skip the constraint retrofit entirely (see note below).

SQLite safety note
------------------
SQLite's ALTER TABLE cannot add CHECK constraints to existing tables, so a
table-rebuild would be required.  However, both transactions and bin_transactions
are *parent* tables that are referenced by child tables:

  transaction_photos.transaction_id → transactions
  checklist_items.linked_transaction_id → transactions
  transactions.bin_transaction_id → bin_transactions

Rebuilding a parent table (RENAME → CREATE → INSERT → DROP) is unsafe:

  * With PRAGMA foreign_keys=OFF (Alembic default): child FK definitions in
    sqlite_master may end up pointing at the now-dropped _old_transactions /
    _old_bin_transactions names, corrupting the schema silently.
  * With PRAGMA foreign_keys=ON: renaming the parent table breaks FK resolution
    and can trigger ON DELETE behaviour (CASCADE / SET NULL), nullifying
    linked_transaction_id or deleting child rows.

Since this project runs PostgreSQL in production, the DB-level constraint is
delivered where it matters.  On SQLite (dev / test environments), the value
normalisation UPDATE above is sufficient; API-level validation and the
SQLAlchemy model CheckConstraints on newly-created databases (Base.metadata
.create_all()) close the gap for tests.

This migration is idempotent on both dialects.
"""
from alembic import op
from sqlalchemy import text

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None

_PURPOSE_CONSTRAINT = "purpose IN ('GENERAL', 'SABHA')"


def _pg_constraint_exists(bind, name: str, table: str) -> bool:
    """Return True if a named constraint exists on the given PostgreSQL table.

    Scoped to the specific table via to_regclass() to avoid false positives from
    same-named constraints on unrelated tables in any schema.

    Uses to_regclass(:table_name) instead of :table::regclass because the
    PostgreSQL cast syntax :: immediately following a bind placeholder confuses
    SQLAlchemy's text() parameter parser, leaving the placeholder unsubstituted.
    """
    return bind.execute(
        text(
            "SELECT 1 FROM pg_constraint "
            "WHERE conname = :name AND conrelid = to_regclass(:table_name)"
        ),
        {"name": name, "table_name": table},
    ).fetchone() is not None


def upgrade() -> None:
    # Normalize invalid values on all dialects before any constraint work.
    op.execute(
        "UPDATE transactions SET purpose = 'GENERAL' WHERE purpose NOT IN ('GENERAL', 'SABHA')"
    )
    op.execute(
        "UPDATE bin_transactions SET purpose = 'GENERAL' WHERE purpose NOT IN ('GENERAL', 'SABHA')"
    )

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # Skip DB-level constraint retrofit on SQLite to avoid parent-table rebuild
        # hazards described in this module's docstring.
        return

    # PostgreSQL: add real DB CHECK constraints, guarded so upgrade is idempotent.
    if not _pg_constraint_exists(bind, "ck_transaction_purpose_valid", "transactions"):
        op.create_check_constraint(
            "ck_transaction_purpose_valid",
            "transactions",
            _PURPOSE_CONSTRAINT,
        )
    if not _pg_constraint_exists(bind, "ck_bin_transaction_purpose_valid", "bin_transactions"):
        op.create_check_constraint(
            "ck_bin_transaction_purpose_valid",
            "bin_transactions",
            _PURPOSE_CONSTRAINT,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # Nothing was added on SQLite, so nothing to remove.
        return

    # Guard drops for idempotency: skip if the constraint was never created.
    if _pg_constraint_exists(bind, "ck_bin_transaction_purpose_valid", "bin_transactions"):
        op.drop_constraint("ck_bin_transaction_purpose_valid", "bin_transactions", type_="check")
    if _pg_constraint_exists(bind, "ck_transaction_purpose_valid", "transactions"):
        op.drop_constraint("ck_transaction_purpose_valid", "transactions", type_="check")
