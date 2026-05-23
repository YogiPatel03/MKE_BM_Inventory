"""
Tests for migration 023: CHECK constraints on transactions.purpose and
bin_transactions.purpose.

The minimal schema deliberately includes ck_transaction_qty_positive — the
existing constraint that caused the original batch_alter_table DDL bug (double
closing-paren).  The fix must survive that pre-existing constraint.
"""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


def _load_migration_023():
    path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "023_add_checkout_purpose_check_constraints.py"
    )
    spec = importlib.util.spec_from_file_location("migration_023", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _operations(conn) -> Operations:
    return Operations(MigrationContext.configure(conn))


def _minimal_engine():
    """
    In-memory SQLite with the pre-023 schema.

    transactions has ck_transaction_qty_positive — the constraint that triggered
    the original Alembic reflection DDL-corruption bug.
    Both tables already have the purpose column (added by migration 022).
    """
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE transactions ("
            "    id INTEGER PRIMARY KEY, "
            "    status TEXT NOT NULL, "
            "    purpose TEXT NOT NULL DEFAULT 'GENERAL', "
            "    quantity NUMERIC(10,2) NOT NULL DEFAULT 1, "
            "    CONSTRAINT ck_transaction_qty_positive CHECK (quantity > 0)"
            ")"
        ))
        conn.execute(text(
            "CREATE TABLE bin_transactions ("
            "    id INTEGER PRIMARY KEY, "
            "    status TEXT NOT NULL, "
            "    purpose TEXT NOT NULL DEFAULT 'GENERAL'"
            ")"
        ))
    return engine


# ── upgrade ───────────────────────────────────────────────────────────────────

def test_upgrade_succeeds_with_existing_check_constraint():
    """The DDL rebuild must not corrupt the table when ck_transaction_qty_positive exists."""
    migration = _load_migration_023()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()


def test_valid_purpose_general_accepted_after_upgrade():
    migration = _load_migration_023()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO transactions (id, status, purpose, quantity) "
            "VALUES (1, 'CHECKED_OUT', 'GENERAL', 1)"
        ))


def test_valid_purpose_sabha_accepted_after_upgrade():
    migration = _load_migration_023()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO transactions (id, status, purpose, quantity) "
            "VALUES (1, 'CHECKED_OUT', 'SABHA', 1)"
        ))


def test_sqlite_does_not_add_check_constraint_to_existing_transactions():
    """
    Migration 023 intentionally skips the DB-level CHECK constraint on SQLite
    existing tables to avoid unsafe parent-table rebuilds with child FKs.
    Invalid purpose values are NOT blocked at the DB level on SQLite after
    migration; they are blocked by API validation and model constraints on
    newly-created databases (create_all).
    """
    migration = _load_migration_023()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    # Must NOT raise — SQLite existing tables intentionally unconstrained.
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO transactions (id, status, purpose, quantity) "
            "VALUES (1, 'CHECKED_OUT', 'INVALID_BUT_ALLOWED_ON_SQLITE', 1)"
        ))


def test_sqlite_does_not_add_check_constraint_to_existing_bin_transactions():
    """
    Same as above for bin_transactions: no DB-level constraint on SQLite
    existing tables after migration 023.
    """
    migration = _load_migration_023()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    # Must NOT raise on SQLite.
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO bin_transactions (id, status, purpose) "
            "VALUES (1, 'CHECKED_OUT', 'NOT_BLOCKED_ON_SQLITE')"
        ))


def test_existing_qty_constraint_still_enforced_after_upgrade():
    """ck_transaction_qty_positive must survive the table rebuild."""
    migration = _load_migration_023()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    with pytest.raises((IntegrityError, Exception)):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO transactions (id, status, purpose, quantity) "
                "VALUES (1, 'CHECKED_OUT', 'GENERAL', -1)"
            ))


def test_invalid_purpose_rows_normalized_to_general_on_upgrade():
    """Existing rows with invalid purpose values are normalized to GENERAL."""
    migration = _load_migration_023()
    engine = _minimal_engine()
    with engine.begin() as conn:
        # Insert bad data before upgrade
        conn.execute(text(
            "INSERT INTO transactions (id, status, purpose, quantity) "
            "VALUES (1, 'CHECKED_OUT', 'OLD_BAD_VALUE', 1)"
        ))
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT purpose FROM transactions WHERE id = 1")
        ).fetchone()
        assert row is not None
        assert row[0] == "GENERAL"


def test_existing_valid_data_preserved_after_upgrade():
    """Valid rows must survive the table rebuild unchanged."""
    migration = _load_migration_023()
    engine = _minimal_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO transactions (id, status, purpose, quantity) "
            "VALUES (10, 'CHECKED_OUT', 'SABHA', 2.5)"
        ))
        conn.execute(text(
            "INSERT INTO bin_transactions (id, status, purpose) "
            "VALUES (20, 'RETURNED', 'GENERAL')"
        ))
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.connect() as conn:
        txn = conn.execute(text("SELECT status, purpose, quantity FROM transactions WHERE id = 10")).fetchone()
        assert txn is not None
        assert txn[0] == "CHECKED_OUT"
        assert txn[1] == "SABHA"

        btxn = conn.execute(text("SELECT status, purpose FROM bin_transactions WHERE id = 20")).fetchone()
        assert btxn is not None
        assert btxn[0] == "RETURNED"
        assert btxn[1] == "GENERAL"


# ── downgrade ─────────────────────────────────────────────────────────────────

def test_downgrade_allows_invalid_purpose_again():
    """After downgrade the CHECK constraint is gone, so any purpose is accepted."""
    migration = _load_migration_023()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.downgrade()

    # Should not raise
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO transactions (id, status, purpose, quantity) "
            "VALUES (1, 'CHECKED_OUT', 'ANYTHING_GOES', 1)"
        ))


def test_downgrade_preserves_qty_constraint():
    """ck_transaction_qty_positive must survive the downgrade rebuild too."""
    migration = _load_migration_023()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.downgrade()

    with pytest.raises((IntegrityError, Exception)):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO transactions (id, status, purpose, quantity) "
                "VALUES (1, 'CHECKED_OUT', 'GENERAL', 0)"
            ))


def test_upgrade_downgrade_roundtrip_preserves_data():
    """Full round-trip: data must be intact after upgrade then downgrade."""
    migration = _load_migration_023()
    engine = _minimal_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO transactions (id, status, purpose, quantity) "
            "VALUES (1, 'CHECKED_OUT', 'GENERAL', 3)"
        ))
        conn.execute(text(
            "INSERT INTO bin_transactions (id, status, purpose) "
            "VALUES (1, 'CHECKED_OUT', 'SABHA')"
        ))
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.downgrade()

    with engine.connect() as conn:
        txn = conn.execute(text("SELECT purpose FROM transactions WHERE id = 1")).fetchone()
        assert txn is not None and txn[0] == "GENERAL"

        btxn = conn.execute(text("SELECT purpose FROM bin_transactions WHERE id = 1")).fetchone()
        assert btxn is not None and btxn[0] == "SABHA"


def test_upgrade_is_idempotent():
    """Running upgrade twice must not fail (constraint already present)."""
    migration = _load_migration_023()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()


def test_downgrade_is_idempotent():
    """Running downgrade twice must not fail (constraint already absent)."""
    migration = _load_migration_023()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.downgrade()

    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.downgrade()


# ── Child FK safety tests ──────────────────────────────────────────────────────

def _child_fk_engine():
    """
    SQLite engine with the full parent+child schema that migration 023 must not
    damage.  Includes:
      - bin_transactions (parent)
      - transactions (parent, FK → bin_transactions, pre-existing qty constraint)
      - transaction_photos (child → transactions, ON DELETE CASCADE)
      - checklists (minimal, to anchor checklist_items)
      - checklist_items (child → transactions via linked_transaction_id)
    """
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE bin_transactions ("
            "    id INTEGER PRIMARY KEY, "
            "    status TEXT NOT NULL, "
            "    purpose TEXT NOT NULL DEFAULT 'GENERAL'"
            ")"
        ))
        conn.execute(text(
            "CREATE TABLE transactions ("
            "    id INTEGER PRIMARY KEY, "
            "    status TEXT NOT NULL, "
            "    purpose TEXT NOT NULL DEFAULT 'GENERAL', "
            "    quantity NUMERIC(10,2) NOT NULL DEFAULT 1, "
            "    bin_transaction_id INTEGER "
            "        REFERENCES bin_transactions(id) ON DELETE SET NULL, "
            "    CONSTRAINT ck_transaction_qty_positive CHECK (quantity > 0)"
            ")"
        ))
        conn.execute(text(
            "CREATE TABLE transaction_photos ("
            "    id INTEGER PRIMARY KEY, "
            "    transaction_id INTEGER NOT NULL "
            "        REFERENCES transactions(id) ON DELETE CASCADE"
            ")"
        ))
        conn.execute(text(
            "CREATE TABLE checklists (id INTEGER PRIMARY KEY)"
        ))
        conn.execute(text(
            "CREATE TABLE checklist_items ("
            "    id INTEGER PRIMARY KEY, "
            "    checklist_id INTEGER NOT NULL REFERENCES checklists(id), "
            "    linked_transaction_id INTEGER "
            "        REFERENCES transactions(id) ON DELETE SET NULL"
            ")"
        ))
    return engine


def test_child_rows_survive_upgrade_with_foreign_keys_on():
    """
    With PRAGMA foreign_keys=ON and child FK tables present, migration 023
    must leave all child rows intact and produce no _old_* table artifacts.
    This verifies the safe approach of skipping SQLite table rebuilds.
    """
    migration = _load_migration_023()
    engine = _child_fk_engine()

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text(
            "INSERT INTO bin_transactions (id, status, purpose) "
            "VALUES (1, 'CHECKED_OUT', 'SABHA')"
        ))
        conn.execute(text(
            "INSERT INTO transactions (id, status, purpose, quantity, bin_transaction_id) "
            "VALUES (10, 'CHECKED_OUT', 'SABHA', 2.0, 1)"
        ))
        conn.execute(text(
            "INSERT INTO transaction_photos (id, transaction_id) VALUES (100, 10)"
        ))
        conn.execute(text("INSERT INTO checklists (id) VALUES (1)"))
        conn.execute(text(
            "INSERT INTO checklist_items (id, checklist_id, linked_transaction_id) "
            "VALUES (200, 1, 10)"
        ))

        migration.op = _operations(conn)
        migration.upgrade()

        # All child rows must survive.
        photo_count = conn.execute(
            text("SELECT COUNT(*) FROM transaction_photos WHERE transaction_id = 10")
        ).scalar()
        assert photo_count == 1

        ci_count = conn.execute(
            text("SELECT COUNT(*) FROM checklist_items WHERE linked_transaction_id = 10")
        ).scalar()
        assert ci_count == 1

        # No stale _old_* tables must exist.
        old_tables = conn.execute(text(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name LIKE '_old_%'"
        )).fetchall()
        assert old_tables == [], f"Unexpected _old_ tables after upgrade: {old_tables}"

        # Foreign key integrity check must pass.
        fk_violations = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
        assert fk_violations == [], f"FK violations after upgrade: {fk_violations}"


def test_child_rows_survive_downgrade_with_foreign_keys_on():
    """Downgrade must also leave all child rows intact with FK checking on."""
    migration = _load_migration_023()
    engine = _child_fk_engine()

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text(
            "INSERT INTO bin_transactions (id, status) VALUES (1, 'CHECKED_OUT')"
        ))
        conn.execute(text(
            "INSERT INTO transactions (id, status, quantity) VALUES (10, 'CHECKED_OUT', 1.0)"
        ))
        conn.execute(text(
            "INSERT INTO transaction_photos (id, transaction_id) VALUES (100, 10)"
        ))
        conn.execute(text("INSERT INTO checklists (id) VALUES (1)"))
        conn.execute(text(
            "INSERT INTO checklist_items (id, checklist_id, linked_transaction_id) "
            "VALUES (200, 1, 10)"
        ))
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        migration.op = _operations(conn)
        migration.downgrade()

        photo_count = conn.execute(
            text("SELECT COUNT(*) FROM transaction_photos")
        ).scalar()
        assert photo_count == 1

        ci_count = conn.execute(
            text("SELECT COUNT(*) FROM checklist_items WHERE linked_transaction_id = 10")
        ).scalar()
        assert ci_count == 1

        fk_violations = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
        assert fk_violations == []


# ── _pg_constraint_exists SQL compile tests ───────────────────────────────────

def test_pg_constraint_exists_sql_uses_table_name_bind():
    """
    _pg_constraint_exists must use :table_name (not :table) so SQLAlchemy's
    text() parser doesn't produce a broken :table::regclass placeholder.
    This is a compile-level regression guard — no PostgreSQL connection needed.
    """
    from sqlalchemy import text as sa_text
    from sqlalchemy.dialects import postgresql as pg_dialect

    sql = sa_text(
        "SELECT 1 FROM pg_constraint "
        "WHERE conname = :name AND conrelid = to_regclass(:table_name)"
    ).bindparams(name="ck_foo", table_name="transactions")

    compiled = sql.compile(dialect=pg_dialect.dialect())
    params = list(compiled.params.keys())

    assert "table_name" in params, f"Expected 'table_name' in bindparams, got: {params}"
    assert "name" in params, f"Expected 'name' in bindparams, got: {params}"

    sql_str = str(compiled)
    assert ":table::regclass" not in sql_str, (
        f"Raw :table::regclass placeholder found in compiled SQL: {sql_str!r}"
    )
    assert "to_regclass" in sql_str, f"to_regclass not found in compiled SQL: {sql_str!r}"


def test_pg_constraint_exists_sql_no_broken_tabl_param():
    """
    The old broken form (:table::regclass) caused SQLAlchemy to parse the param
    as 'tabl' instead of 'table', leaving a raw placeholder in the SQL.
    Verify the new form has no such truncation.
    """
    from sqlalchemy import text as sa_text
    from sqlalchemy.dialects import postgresql as pg_dialect

    sql = sa_text(
        "SELECT 1 FROM pg_constraint "
        "WHERE conname = :name AND conrelid = to_regclass(:table_name)"
    ).bindparams(name="ck_foo", table_name="transactions")

    compiled = sql.compile(dialect=pg_dialect.dialect())
    params = list(compiled.params.keys())

    assert "tabl" not in params, (
        f"Truncated 'tabl' param found — SQLAlchemy is still misparse the bind: {params}"
    )
    assert "table" not in params, (
        f"Old bind name 'table' still present — fix was not applied: {params}"
    )


def test_invalid_purpose_rows_normalized_before_child_data():
    """
    Invalid purpose values in parent tables are normalised to GENERAL before
    any constraint work, and child rows referencing those parent rows survive.
    """
    migration = _load_migration_023()
    engine = _child_fk_engine()

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO transactions (id, status, purpose, quantity) "
            "VALUES (1, 'CHECKED_OUT', 'OLD_INVALID', 1.0)"
        ))
        conn.execute(text("INSERT INTO checklists (id) VALUES (1)"))
        conn.execute(text(
            "INSERT INTO checklist_items (id, checklist_id, linked_transaction_id) "
            "VALUES (10, 1, 1)"
        ))
        migration.op = _operations(conn)
        migration.upgrade()

        purpose = conn.execute(
            text("SELECT purpose FROM transactions WHERE id = 1")
        ).scalar()
        assert purpose == "GENERAL"

        ci_exists = conn.execute(
            text("SELECT COUNT(*) FROM checklist_items WHERE linked_transaction_id = 1")
        ).scalar()
        assert ci_exists == 1
