"""
Tests for migration 021: adds requires_request to items table.
"""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def _load_migration_021():
    path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "021_add_requires_request_to_items.py"
    )
    spec = importlib.util.spec_from_file_location("migration_021", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _operations(conn) -> Operations:
    return Operations(MigrationContext.configure(conn))


def test_migration_adds_requires_request_column():
    migration = _load_migration_021()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE items ("
                "id INTEGER PRIMARY KEY, "
                "name TEXT NOT NULL, "
                "is_consumable INTEGER NOT NULL DEFAULT 0"
                ")"
            )
        )
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.connect() as conn:
        columns = {col["name"] for col in inspect(engine).get_columns("items")}
        assert "requires_request" in columns


def test_existing_rows_default_to_false_after_migration():
    migration = _load_migration_021()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE items ("
                "id INTEGER PRIMARY KEY, "
                "name TEXT NOT NULL, "
                "is_consumable INTEGER NOT NULL DEFAULT 0"
                ")"
            )
        )
        conn.execute(text("INSERT INTO items (id, name, is_consumable) VALUES (1, 'Legacy Item', 0)"))
        migration.op = _operations(conn)
        migration.upgrade()

    with engine.connect() as conn:
        row = conn.execute(text("SELECT requires_request FROM items WHERE id = 1")).fetchone()
        assert row is not None
        assert row[0] == 0
