"""
Tests for migration 020 case-insensitive SKU/bin-number protections.
"""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


def _load_migration_020():
    path = Path(__file__).parents[1] / "migrations" / "versions" / "020_add_bin_number_to_bins.py"
    spec = importlib.util.spec_from_file_location("migration_020", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _operations(conn) -> Operations:
    return Operations(MigrationContext.configure(conn))


def test_migration_duplicate_detection_fails_clearly_for_item_sku(monkeypatch):
    migration = _load_migration_020()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, sku TEXT)"))
        conn.execute(text("INSERT INTO items (id, sku) VALUES (1, 'SMC1'), (2, 'smc1')"))
        monkeypatch.setattr(migration, "op", _operations(conn))

        with pytest.raises(RuntimeError, match="items.sku"):
            migration._raise_if_case_insensitive_duplicates("items", "sku", "items.sku")


def test_migration_duplicate_detection_fails_clearly_for_bin_number(monkeypatch):
    migration = _load_migration_020()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE bins (id INTEGER PRIMARY KEY, bin_number TEXT)"))
        conn.execute(text("INSERT INTO bins (id, bin_number) VALUES (1, 'SMCD1'), (2, 'smcd1')"))
        monkeypatch.setattr(migration, "op", _operations(conn))

        with pytest.raises(RuntimeError, match="bins.bin_number"):
            migration._raise_if_case_insensitive_duplicates("bins", "bin_number", "bins.bin_number")


def test_migration_functional_unique_index_blocks_case_variant_sku(monkeypatch):
    migration = _load_migration_020()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, sku TEXT)"))
        monkeypatch.setattr(migration, "op", _operations(conn))
        migration._create_case_insensitive_unique_index("ux_items_sku_lower", "items", "sku")

        conn.execute(text("INSERT INTO items (id, sku) VALUES (1, 'SMC1')"))
        with pytest.raises(IntegrityError):
            conn.execute(text("INSERT INTO items (id, sku) VALUES (2, 'smc1')"))


def test_migration_functional_unique_index_blocks_case_variant_bin_number(monkeypatch):
    migration = _load_migration_020()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE bins (id INTEGER PRIMARY KEY, bin_number TEXT)"))
        monkeypatch.setattr(migration, "op", _operations(conn))
        migration._create_case_insensitive_unique_index(
            "ux_bins_bin_number_lower", "bins", "bin_number"
        )

        conn.execute(text("INSERT INTO bins (id, bin_number) VALUES (1, 'SMCD1')"))
        with pytest.raises(IntegrityError):
            conn.execute(text("INSERT INTO bins (id, bin_number) VALUES (2, 'smcd1')"))
