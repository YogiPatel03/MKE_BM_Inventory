"""Add purpose column to inventory_requests

Revision ID: 025
Revises: 024
Create Date: 2026-05-23

Changes:
  - Add purpose VARCHAR(20) NOT NULL DEFAULT 'GENERAL' to inventory_requests.
  - Normalize any pre-existing invalid purpose values to 'GENERAL'.
  - PostgreSQL: add real DB-level CHECK constraint
    ck_inventory_request_purpose_valid (purpose IN ('GENERAL', 'SABHA')).
  - SQLite: skip DB-level constraint retrofit (see SQLite safety note below).

SQLite safety note
------------------
Unlike transactions/bin_transactions in migration 023, inventory_requests has
no child tables with FK references to it, so a table rebuild would be safe.
However, the same project policy is applied for consistency: skip the DB-level
CHECK constraint on SQLite existing tables and rely on:
  - API/schema enum validation (CheckoutPurpose)
  - The model's CheckConstraint, which is enforced on freshly-created databases
    (Base.metadata.create_all()).
  - The NOT NULL + server_default = 'GENERAL' column definition.

PostgreSQL receives the real DB-level constraint because that is where this
project runs in production.

Idempotency
-----------
Both upgrade() and downgrade() guard against double-execution:
  - _column_exists() prevents a second ADD COLUMN from failing.
  - _pg_constraint_exists() prevents a second CREATE/DROP CONSTRAINT from
    failing on PostgreSQL.
"""
from alembic import op
from sqlalchemy import text

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None

_CONSTRAINT_NAME = "ck_inventory_request_purpose_valid"
_PURPOSE_CONSTRAINT = "purpose IN ('GENERAL', 'SABHA')"


def _column_exists(bind, table: str, column: str) -> bool:
    """Return True if the column already exists in the table (both dialects)."""
    if bind.dialect.name == "postgresql":
        return bind.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": column},
        ).fetchone() is not None
    # SQLite: PRAGMA table_info returns one row per column; row[1] is the name.
    rows = bind.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def _pg_constraint_exists(bind, name: str, table: str) -> bool:
    """Return True if a named constraint exists on the given PostgreSQL table.

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
    bind = op.get_bind()

    # Add the column if not already present (idempotent).
    # Raw SQL is used so that SQLite accepts NOT NULL with a DEFAULT inline,
    # which backfills all existing rows to 'GENERAL' without a separate UPDATE.
    if not _column_exists(bind, "inventory_requests", "purpose"):
        bind.execute(text(
            "ALTER TABLE inventory_requests "
            "ADD COLUMN purpose VARCHAR(20) NOT NULL DEFAULT 'GENERAL'"
        ))

    # Normalize NULL and any invalid purpose values to 'GENERAL'.
    # NULL must be included explicitly: SQL's NOT IN does not match NULL rows.
    op.execute(
        "UPDATE inventory_requests "
        "SET purpose = 'GENERAL' "
        "WHERE purpose IS NULL OR purpose NOT IN ('GENERAL', 'SABHA')"
    )

    if bind.dialect.name == "sqlite":
        # Skip DB-level constraint retrofit on SQLite — see module docstring.
        return

    # PostgreSQL: enforce DEFAULT and NOT NULL unconditionally so that the drift
    # path (column already existed, possibly nullable) is repaired just like the
    # fresh-add path.  These statements are idempotent: they are no-ops if the
    # default/constraint is already set.
    bind.execute(text(
        "ALTER TABLE inventory_requests ALTER COLUMN purpose SET DEFAULT 'GENERAL'"
    ))
    bind.execute(text(
        "ALTER TABLE inventory_requests ALTER COLUMN purpose SET NOT NULL"
    ))

    # PostgreSQL: add real DB CHECK constraint, guarded so upgrade is idempotent.
    if not _pg_constraint_exists(bind, _CONSTRAINT_NAME, "inventory_requests"):
        op.create_check_constraint(
            _CONSTRAINT_NAME,
            "inventory_requests",
            _PURPOSE_CONSTRAINT,
        )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name != "sqlite":
        # PostgreSQL: drop the CHECK constraint first (guarded for idempotency).
        if _pg_constraint_exists(bind, _CONSTRAINT_NAME, "inventory_requests"):
            op.drop_constraint(_CONSTRAINT_NAME, "inventory_requests", type_="check")

    # Drop the purpose column on all dialects.
    # SQLite 3.35+ supports ALTER TABLE DROP COLUMN natively; Alembic 1.14
    # handles it correctly. inventory_requests has no child FK references, so
    # a table rebuild (if Alembic falls back to one) is also safe.
    if _column_exists(bind, "inventory_requests", "purpose"):
        op.drop_column("inventory_requests", "purpose")
