"""
Tests for migration 022: checklist_assignment_defaults table and checkout purpose fields.
"""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


def _load_migration_022():
    path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "022_checklist_defaults_and_checkout_purpose.py"
    )
    spec = importlib.util.spec_from_file_location("migration_022", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _operations(conn) -> Operations:
    return Operations(MigrationContext.configure(conn))


def _minimal_engine():
    """In-memory SQLite with the tables that migration 022 depends on."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        # users table (FK target for checklist_assignment_defaults)
        conn.execute(text(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, "
            "username TEXT NOT NULL"
            ")"
        ))
        # transactions table (needs purpose column added)
        conn.execute(text(
            "CREATE TABLE transactions ("
            "id INTEGER PRIMARY KEY, "
            "status TEXT NOT NULL"
            ")"
        ))
        # bin_transactions table (needs purpose column added)
        conn.execute(text(
            "CREATE TABLE bin_transactions ("
            "id INTEGER PRIMARY KEY, "
            "status TEXT NOT NULL"
            ")"
        ))
        # items table required by migration 021 prerequisite chain; not needed here
        # but include to keep environment realistic
        conn.execute(text(
            "CREATE TABLE items ("
            "id INTEGER PRIMARY KEY, "
            "requires_request INTEGER NOT NULL DEFAULT 0"
            ")"
        ))
    return engine


# ── checklist_assignment_defaults ─────────────────────────────────────────────

def test_migration_creates_checklist_assignment_defaults_table():
    migration = _load_migration_022()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.connect() as conn:
        tables = inspect(engine).get_table_names()
        assert "checklist_assignment_defaults" in tables


def test_checklist_defaults_table_has_expected_columns():
    migration = _load_migration_022()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    col_names = {c["name"] for c in inspect(engine).get_columns("checklist_assignment_defaults")}
    assert col_names >= {"id", "group_name", "user_id", "assigned_by_id", "is_active", "created_at", "updated_at"}


def test_checklist_defaults_is_active_defaults_to_true():
    migration = _load_migration_022()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, username) VALUES (1, 'alice'), (2, 'bob')"))
        conn.execute(text(
            "INSERT INTO checklist_assignment_defaults (group_name, user_id, assigned_by_id) "
            "VALUES ('GROUP_1', 1, 2)"
        ))
        row = conn.execute(
            text("SELECT is_active FROM checklist_assignment_defaults WHERE user_id = 1")
        ).fetchone()
        assert row is not None
        assert row[0] in (1, True)


def test_partial_unique_index_blocks_duplicate_active_defaults():
    """Two active rows for the same (group_name, user_id) must be rejected."""
    migration = _load_migration_022()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, username) VALUES (1, 'alice'), (2, 'bob')"))
        conn.execute(text(
            "INSERT INTO checklist_assignment_defaults (group_name, user_id, assigned_by_id, is_active) "
            "VALUES ('GROUP_1', 1, 2, 1)"
        ))

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO checklist_assignment_defaults (group_name, user_id, assigned_by_id, is_active) "
                "VALUES ('GROUP_1', 1, 2, 1)"
            ))


def test_partial_unique_index_allows_inactive_duplicate():
    """An inactive row for the same (group_name, user_id) must be allowed."""
    migration = _load_migration_022()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, username) VALUES (1, 'alice'), (2, 'bob')"))
        # Insert one active and one inactive for the same group/user
        conn.execute(text(
            "INSERT INTO checklist_assignment_defaults (group_name, user_id, assigned_by_id, is_active) "
            "VALUES ('GROUP_1', 1, 2, 0)"
        ))
        # This second insert (also inactive) should be allowed — no unique violation
        conn.execute(text(
            "INSERT INTO checklist_assignment_defaults (group_name, user_id, assigned_by_id, is_active) "
            "VALUES ('GROUP_1', 1, 2, 0)"
        ))


def test_reactivation_after_deactivation_allowed():
    """Deactivating then re-adding a user must succeed."""
    migration = _load_migration_022()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, username) VALUES (1, 'alice'), (2, 'bob')"))
        # Original active row
        conn.execute(text(
            "INSERT INTO checklist_assignment_defaults (id, group_name, user_id, assigned_by_id, is_active) "
            "VALUES (1, 'GROUP_1', 1, 2, 1)"
        ))
        # Deactivate it
        conn.execute(text(
            "UPDATE checklist_assignment_defaults SET is_active = 0 WHERE id = 1"
        ))
        # Re-add as active — must succeed
        conn.execute(text(
            "INSERT INTO checklist_assignment_defaults (group_name, user_id, assigned_by_id, is_active) "
            "VALUES ('GROUP_1', 1, 2, 1)"
        ))


# ── purpose columns ───────────────────────────────────────────────────────────

def test_migration_adds_purpose_to_transactions():
    migration = _load_migration_022()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    col_names = {c["name"] for c in inspect(engine).get_columns("transactions")}
    assert "purpose" in col_names


def test_migration_adds_purpose_to_bin_transactions():
    migration = _load_migration_022()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    col_names = {c["name"] for c in inspect(engine).get_columns("bin_transactions")}
    assert "purpose" in col_names


def test_existing_transaction_rows_default_to_general():
    migration = _load_migration_022()
    engine = _minimal_engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO transactions (id, status) VALUES (1, 'CHECKED_OUT')"))
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.connect() as conn:
        row = conn.execute(text("SELECT purpose FROM transactions WHERE id = 1")).fetchone()
        assert row is not None
        assert row[0] == "GENERAL"


def test_existing_bin_transaction_rows_default_to_general():
    migration = _load_migration_022()
    engine = _minimal_engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO bin_transactions (id, status) VALUES (1, 'CHECKED_OUT')"))
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.connect() as conn:
        row = conn.execute(text("SELECT purpose FROM bin_transactions WHERE id = 1")).fetchone()
        assert row is not None
        assert row[0] == "GENERAL"


# ── downgrade ─────────────────────────────────────────────────────────────────

def test_downgrade_removes_all_additions():
    migration = _load_migration_022()
    engine = _minimal_engine()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.downgrade()

    tables = inspect(engine).get_table_names()
    assert "checklist_assignment_defaults" not in tables

    txn_cols = {c["name"] for c in inspect(engine).get_columns("transactions")}
    assert "purpose" not in txn_cols

    bin_cols = {c["name"] for c in inspect(engine).get_columns("bin_transactions")}
    assert "purpose" not in bin_cols
