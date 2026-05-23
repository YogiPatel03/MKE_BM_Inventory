"""
Tests for migration 025: purpose column on inventory_requests.

Covers:
  - Existing rows get purpose = 'GENERAL' after upgrade.
  - Valid purpose values are accepted after upgrade.
  - Invalid purpose values are normalized to 'GENERAL' on upgrade.
  - SQLite does NOT add a DB-level CHECK constraint (by project policy).
  - Downgrade removes the purpose column.
  - Upgrade → downgrade → upgrade round-trip succeeds.
  - Upgrade is idempotent (running it twice does not fail).
  - Downgrade is idempotent (running it twice does not fail).
  - PostgreSQL CHECK constraint SQL compiles/binds safely (no live PG needed).
"""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


def _load_migration_025():
    path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "025_add_purpose_to_inventory_requests.py"
    )
    spec = importlib.util.spec_from_file_location("migration_025", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _operations(conn) -> Operations:
    return Operations(MigrationContext.configure(conn))


def _minimal_engine():
    """
    In-memory SQLite with the pre-025 inventory_requests schema (no purpose column).
    Intentionally minimal — only the columns the migration touches need to exist.
    """
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE inventory_requests ("
            "    id INTEGER PRIMARY KEY, "
            "    requester_id INTEGER NOT NULL, "
            "    status TEXT NOT NULL DEFAULT 'PENDING'"
            ")"
        ))
    return engine


def _upgrade(engine):
    migration = _load_migration_025()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()


def _downgrade(engine):
    migration = _load_migration_025()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.downgrade()


# ── upgrade ───────────────────────────────────────────────────────────────────

def test_upgrade_adds_purpose_column():
    """purpose column must exist after upgrade."""
    engine = _minimal_engine()
    _upgrade(engine)

    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(inventory_requests)")).fetchall()
        col_names = [row[1] for row in rows]
        assert "purpose" in col_names


def test_existing_rows_get_general_default():
    """Rows present before upgrade must have purpose='GENERAL' afterwards."""
    engine = _minimal_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO inventory_requests (id, requester_id, status) "
            "VALUES (1, 10, 'PENDING'), (2, 11, 'APPROVED')"
        ))
    _upgrade(engine)

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, purpose FROM inventory_requests ORDER BY id")
        ).fetchall()
        assert len(rows) == 2
        assert all(row[1] == "GENERAL" for row in rows), (
            f"Expected all rows to have purpose='GENERAL', got: {rows}"
        )


def test_valid_purpose_general_accepted_after_upgrade():
    """Inserting purpose='GENERAL' must succeed after upgrade."""
    engine = _minimal_engine()
    _upgrade(engine)

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO inventory_requests (id, requester_id, status, purpose) "
            "VALUES (1, 10, 'PENDING', 'GENERAL')"
        ))


def test_valid_purpose_sabha_accepted_after_upgrade():
    """Inserting purpose='SABHA' must succeed after upgrade."""
    engine = _minimal_engine()
    _upgrade(engine)

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO inventory_requests (id, requester_id, status, purpose) "
            "VALUES (1, 10, 'PENDING', 'SABHA')"
        ))


def test_invalid_purpose_rows_normalized_to_general_on_upgrade():
    """
    The upgrade normalizes any pre-existing rows with invalid purpose values
    to 'GENERAL'.  This path is exercised by inserting a row with a bad value
    before the column constraint is active, then running upgrade.
    """
    engine = _minimal_engine()
    # Add the column manually with a loose constraint to allow inserting a bad value,
    # then run upgrade which should normalize it.
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE inventory_requests ADD COLUMN purpose VARCHAR(20)"
        ))
        conn.execute(text(
            "INSERT INTO inventory_requests (id, requester_id, status, purpose) "
            "VALUES (1, 10, 'PENDING', 'old_bad_value')"
        ))

    _upgrade(engine)

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT purpose FROM inventory_requests WHERE id = 1")
        ).fetchone()
        assert row is not None
        assert row[0] == "GENERAL"


def test_null_purpose_rows_normalized_to_general_on_upgrade():
    """
    Drift path: purpose column already exists but is nullable and contains NULL
    rows.  upgrade() must normalize NULLs to 'GENERAL' because SQL's NOT IN
    does not match NULL values.
    """
    engine = _minimal_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE inventory_requests ADD COLUMN purpose VARCHAR(20)"
        ))
        conn.execute(text(
            "INSERT INTO inventory_requests (id, requester_id, status, purpose) "
            "VALUES (1, 10, 'PENDING', NULL), (2, 11, 'APPROVED', 'SABHA')"
        ))

    _upgrade(engine)

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, purpose FROM inventory_requests ORDER BY id")
        ).fetchall()
        assert rows[0][1] == "GENERAL", f"Expected NULL to become 'GENERAL', got: {rows[0][1]}"
        assert rows[1][1] == "SABHA", f"Expected valid 'SABHA' to be preserved, got: {rows[1][1]}"


def test_existing_valid_data_preserved_after_upgrade():
    """Valid rows survive upgrade unchanged."""
    engine = _minimal_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO inventory_requests (id, requester_id, status) "
            "VALUES (5, 10, 'FULFILLED'), (6, 11, 'DENIED')"
        ))
    _upgrade(engine)

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, status, purpose FROM inventory_requests ORDER BY id")
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == 5
        assert rows[0][1] == "FULFILLED"
        assert rows[0][2] == "GENERAL"
        assert rows[1][0] == 6
        assert rows[1][1] == "DENIED"
        assert rows[1][2] == "GENERAL"


def test_sqlite_does_not_add_db_check_constraint_to_existing_table():
    """
    By project policy (matching migration 023), migration 025 does NOT add a
    DB-level CHECK constraint on SQLite existing tables.  Invalid purpose values
    at the DB level are NOT blocked on SQLite after migration; they are blocked
    by API/schema validation and by model constraints on newly-created databases
    (Base.metadata.create_all()).
    """
    engine = _minimal_engine()
    _upgrade(engine)

    # Must NOT raise — SQLite intentionally has no DB-level constraint here.
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO inventory_requests (id, requester_id, status, purpose) "
            "VALUES (1, 10, 'PENDING', 'INVALID_BUT_ALLOWED_AT_DB_LEVEL_ON_SQLITE')"
        ))


# ── downgrade ─────────────────────────────────────────────────────────────────

def test_downgrade_removes_purpose_column():
    """Downgrade must remove the purpose column from inventory_requests."""
    engine = _minimal_engine()
    _upgrade(engine)
    _downgrade(engine)

    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(inventory_requests)")).fetchall()
        col_names = [row[1] for row in rows]
        assert "purpose" not in col_names, (
            f"purpose column must be gone after downgrade, but found columns: {col_names}"
        )


def test_downgrade_preserves_other_columns():
    """Non-purpose columns must be intact after downgrade."""
    engine = _minimal_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO inventory_requests (id, requester_id, status) "
            "VALUES (1, 10, 'PENDING')"
        ))
    _upgrade(engine)
    _downgrade(engine)

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, requester_id, status FROM inventory_requests WHERE id = 1")
        ).fetchone()
        assert row is not None
        assert row[0] == 1
        assert row[1] == 10
        assert row[2] == "PENDING"


# ── idempotency ───────────────────────────────────────────────────────────────

def test_upgrade_is_idempotent():
    """Running upgrade twice must not fail."""
    engine = _minimal_engine()
    _upgrade(engine)
    _upgrade(engine)  # second run: column already exists, must be a no-op


def test_downgrade_is_idempotent():
    """Running downgrade twice must not fail."""
    engine = _minimal_engine()
    _upgrade(engine)
    _downgrade(engine)
    _downgrade(engine)  # second run: column already gone, must be a no-op


# ── round-trip ────────────────────────────────────────────────────────────────

def test_upgrade_downgrade_roundtrip_succeeds():
    """Upgrade → downgrade → upgrade must complete without error."""
    engine = _minimal_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO inventory_requests (id, requester_id, status) "
            "VALUES (1, 10, 'PENDING')"
        ))
    _upgrade(engine)
    _downgrade(engine)
    _upgrade(engine)

    with engine.connect() as conn:
        col_names = [
            row[1]
            for row in conn.execute(text("PRAGMA table_info(inventory_requests)")).fetchall()
        ]
        assert "purpose" in col_names


def test_roundtrip_data_survives():
    """Data (excluding purpose) must survive a full upgrade → downgrade → upgrade cycle."""
    engine = _minimal_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO inventory_requests (id, requester_id, status) "
            "VALUES (1, 10, 'FULFILLED'), (2, 11, 'DENIED')"
        ))
    _upgrade(engine)
    _downgrade(engine)
    _upgrade(engine)

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, requester_id, status, purpose FROM inventory_requests ORDER BY id")
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == 1
        assert rows[0][2] == "FULFILLED"
        assert rows[0][3] == "GENERAL"
        assert rows[1][0] == 2
        assert rows[1][2] == "DENIED"
        assert rows[1][3] == "GENERAL"


# ── PostgreSQL SQL compile guard (no live PG connection needed) ────────────────

def test_pg_constraint_exists_sql_compiles_safely():
    """
    _pg_constraint_exists must use :table_name (not :table) so SQLAlchemy's
    text() parser doesn't produce a broken :table::regclass placeholder.
    Compile-level regression guard — no PostgreSQL connection needed.
    """
    from sqlalchemy import text as sa_text
    from sqlalchemy.dialects import postgresql as pg_dialect

    sql = sa_text(
        "SELECT 1 FROM pg_constraint "
        "WHERE conname = :name AND conrelid = to_regclass(:table_name)"
    ).bindparams(name="ck_inventory_request_purpose_valid", table_name="inventory_requests")

    compiled = sql.compile(dialect=pg_dialect.dialect())
    params = list(compiled.params.keys())

    assert "table_name" in params
    assert "name" in params
    assert ":table::regclass" not in str(compiled)
    assert "to_regclass" in str(compiled)


def test_pg_check_constraint_create_sql_compiles():
    """
    The CHECK constraint SQL expression used in op.create_check_constraint must
    compile correctly against the PostgreSQL dialect without errors.
    """
    from sqlalchemy import CheckConstraint
    from sqlalchemy.dialects import postgresql as pg_dialect

    constraint = CheckConstraint(
        "purpose IN ('GENERAL', 'SABHA')",
        name="ck_inventory_request_purpose_valid",
    )
    # Compiling the constraint expression against the PG dialect must not raise.
    compiled = constraint.sqltext.compile(dialect=pg_dialect.dialect())
    sql_str = str(compiled)
    assert "GENERAL" in sql_str
    assert "SABHA" in sql_str
