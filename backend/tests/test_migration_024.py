"""
Tests for migration 024: unique partial indexes on checklist_items with
smart duplicate survivor selection and completion-state merging.
"""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


def _load_migration_024():
    path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "024_checklist_item_unique_linked_ids.py"
    )
    spec = importlib.util.spec_from_file_location("migration_024", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _operations(conn) -> Operations:
    return Operations(MigrationContext.configure(conn))


def _engine():
    """
    Minimal in-memory SQLite with the checklist_items schema that migration 024
    operates on.  Foreign key constraints are intentionally omitted so the test
    can insert rows without setting up the full parent-table graph.
    """
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE checklist_items ("
            "    id INTEGER PRIMARY KEY, "
            "    linked_transaction_id INTEGER, "
            "    linked_bin_transaction_id INTEGER, "
            "    is_completed INTEGER NOT NULL DEFAULT 0, "
            "    completed_at TEXT, "
            "    completed_by_user_id INTEGER, "
            "    completion_notes TEXT, "
            "    photo_requested_via_telegram INTEGER NOT NULL DEFAULT 0, "
            "    auto_type TEXT, "
            "    is_auto_generated INTEGER NOT NULL DEFAULT 0, "
            "    checklist_id INTEGER NOT NULL DEFAULT 1, "
            "    title TEXT NOT NULL DEFAULT 'task', "
            "    item_order INTEGER NOT NULL DEFAULT 0"
            ")"
        ))
    return engine


def _upgrade(engine):
    migration = _load_migration_024()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.upgrade()


def _downgrade(engine):
    migration = _load_migration_024()
    with engine.begin() as conn:
        migration.op = _operations(conn)
        migration.downgrade()


def _rows(engine, where=""):
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT id, linked_transaction_id, linked_bin_transaction_id, "
            "is_completed, completed_at, completed_by_user_id, completion_notes, "
            "photo_requested_via_telegram, auto_type "
            f"FROM checklist_items {where}"
        )).fetchall()


# ── No-duplicate cases ────────────────────────────────────────────────────────

def test_no_duplicates_leaves_rows_unchanged():
    """Non-duplicate rows survive upgrade untouched."""
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items (id, linked_transaction_id, is_completed) "
            "VALUES (1, 1, 0), (2, 2, 1)"
        ))
    _upgrade(engine)
    assert len(_rows(engine)) == 2


def test_null_linked_ids_not_affected():
    """Rows with NULL linked ids are never touched by the dedup."""
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items (id, linked_transaction_id, is_completed) "
            "VALUES (1, NULL, 0), (2, NULL, 1)"
        ))
    _upgrade(engine)
    assert len(_rows(engine)) == 2


# ── Transaction-id dedup: survivor selection ──────────────────────────────────

def test_completed_row_wins_over_pending_even_with_higher_id():
    """
    When one duplicate is completed and the other is pending, the completed row
    is the survivor regardless of which has the lower id.
    """
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items "
            "(id, linked_transaction_id, is_completed, completed_at, auto_type) "
            "VALUES "
            "(1, 42, 0, NULL, 'ITEM_RETURN'), "      # pending, lower id
            "(2, 42, 1, '2026-01-10T12:00:00', 'ITEM_RETURN')"   # completed, higher id
        ))
    _upgrade(engine)

    rows = _rows(engine, "WHERE linked_transaction_id = 42")
    assert len(rows) == 1, "Exactly one row must survive"
    survivor = rows[0]
    assert survivor[0] == 2, "Completed row (id=2) must be the survivor"
    assert survivor[3] == 1, "is_completed must be True"
    assert survivor[4] == "2026-01-10T12:00:00"


def test_among_pending_duplicates_lowest_id_wins():
    """When all duplicates are pending, the lowest id is the survivor."""
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items "
            "(id, linked_transaction_id, is_completed, auto_type) "
            "VALUES (5, 99, 0, 'ITEM_RETURN'), (3, 99, 0, 'ITEM_RETURN')"
        ))
    _upgrade(engine)

    rows = _rows(engine, "WHERE linked_transaction_id = 99")
    assert len(rows) == 1
    assert rows[0][0] == 3, "Lowest id (3) must win among pending rows"


def test_among_completed_prefers_row_with_most_data():
    """
    Among multiple completed rows, the one with completed_by_user_id and
    completion_notes beats one without, even if it has a higher id.
    """
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items "
            "(id, linked_transaction_id, is_completed, completed_at, "
            " completed_by_user_id, completion_notes, auto_type) "
            "VALUES "
            "(1, 7, 1, '2026-01-01T10:00:00', NULL, NULL, 'ITEM_RETURN'), "
            "(2, 7, 1, '2026-01-01T11:00:00', 5, 'done', 'ITEM_RETURN')"
        ))
    _upgrade(engine)

    rows = _rows(engine, "WHERE linked_transaction_id = 7")
    assert len(rows) == 1
    survivor = rows[0]
    # id=2 has more data → lower score → wins
    assert survivor[0] == 2
    assert survivor[5] == 5   # completed_by_user_id
    assert survivor[6] == "done"  # completion_notes


# ── State merging ─────────────────────────────────────────────────────────────

def test_completed_survivor_inherits_missing_fields_from_pending_discard():
    """
    Completion state on a discarded pending row is merged into the completed
    survivor when the survivor's own fields are NULL/False.
    """
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items "
            "(id, linked_transaction_id, is_completed, completed_at, "
            " completed_by_user_id, completion_notes, photo_requested_via_telegram) "
            "VALUES "
            "(1, 55, 1, '2026-02-01T09:00:00', NULL, NULL, 0), "  # completed, missing by/notes
            "(2, 55, 0, NULL, 7, 'manual note', 1)"               # pending but has extra fields
        ))
    _upgrade(engine)

    rows = _rows(engine, "WHERE linked_transaction_id = 55")
    assert len(rows) == 1
    s = rows[0]
    assert s[0] == 1                    # completed row (id=1) survived
    assert s[3] == 1                    # is_completed preserved
    assert s[5] == 7                    # completed_by_user_id merged from discard
    assert s[6] == "manual note"        # completion_notes merged
    assert s[7] in (1, True)            # photo_requested_via_telegram merged


def test_merge_does_not_overwrite_existing_survivor_fields():
    """
    Merge only fills NULL/False fields on the survivor; it does not
    overwrite values the survivor already has.
    """
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items "
            "(id, linked_transaction_id, is_completed, completed_at, "
            " completed_by_user_id, completion_notes) "
            "VALUES "
            "(1, 11, 1, '2026-03-01T08:00:00', 3, 'original note'), "
            "(2, 11, 0, '2026-03-02T09:00:00', 9, 'other note')"
        ))
    _upgrade(engine)

    rows = _rows(engine, "WHERE linked_transaction_id = 11")
    assert len(rows) == 1
    s = rows[0]
    assert s[0] == 1                         # completed row survived
    assert s[4] == "2026-03-01T08:00:00"    # own completed_at kept
    assert s[5] == 3                         # own completed_by_user_id kept
    assert s[6] == "original note"           # own completion_notes kept


# ── Bin transaction dedup ─────────────────────────────────────────────────────

def test_bin_txn_completed_row_wins_over_pending():
    """Same survivor-selection logic applies to linked_bin_transaction_id."""
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items "
            "(id, linked_bin_transaction_id, is_completed, completed_at, auto_type) "
            "VALUES "
            "(10, 88, 0, NULL, 'BIN_RETURN'), "
            "(20, 88, 1, '2026-04-01T15:00:00', 'BIN_RETURN')"
        ))
    _upgrade(engine)

    rows = _rows(engine, "WHERE linked_bin_transaction_id = 88")
    assert len(rows) == 1
    assert rows[0][0] == 20  # completed row (id=20) survived


def test_bin_txn_completion_state_merged():
    """Completion state from a discarded bin row merges into the survivor."""
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items "
            "(id, linked_bin_transaction_id, is_completed, completed_at, "
            " completed_by_user_id, completion_notes, photo_requested_via_telegram) "
            "VALUES "
            "(10, 77, 1, '2026-04-05T12:00:00', NULL, NULL, 0), "
            "(20, 77, 0, NULL, 4, 'bin returned', 1)"
        ))
    _upgrade(engine)

    rows = _rows(engine, "WHERE linked_bin_transaction_id = 77")
    assert len(rows) == 1
    s = rows[0]
    assert s[0] == 10               # completed row survived
    assert s[5] == 4                # completed_by_user_id merged
    assert s[6] == "bin returned"  # completion_notes merged
    assert s[7] in (1, True)        # photo flag merged


# ── Unknown auto_type rows ────────────────────────────────────────────────────

def test_unexpected_auto_type_included_safely_in_dedup():
    """
    Rows with unexpected auto_type values sharing a linked_transaction_id are
    included in dedup (not silently dropped without merging state).
    """
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items "
            "(id, linked_transaction_id, is_completed, completion_notes, auto_type) "
            "VALUES "
            "(1, 33, 1, 'note from unknown', 'FUTURE_TYPE'), "
            "(2, 33, 0, NULL, 'ITEM_RETURN')"
        ))
    _upgrade(engine)

    rows = _rows(engine, "WHERE linked_transaction_id = 33")
    assert len(rows) == 1
    s = rows[0]
    assert s[0] == 1                       # completed FUTURE_TYPE row survived
    assert s[6] == "note from unknown"     # its own note preserved


# ── Unique index creation ─────────────────────────────────────────────────────

def test_unique_index_prevents_new_txn_duplicate():
    """After upgrade, inserting a second row for the same linked_transaction_id raises."""
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items (id, linked_transaction_id) VALUES (1, 5)"
        ))
    _upgrade(engine)

    with pytest.raises((IntegrityError, Exception)):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO checklist_items (id, linked_transaction_id) VALUES (2, 5)"
            ))


def test_unique_index_prevents_new_bin_txn_duplicate():
    """After upgrade, inserting a second row for the same linked_bin_transaction_id raises."""
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items (id, linked_bin_transaction_id) VALUES (1, 9)"
        ))
    _upgrade(engine)

    with pytest.raises((IntegrityError, Exception)):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO checklist_items (id, linked_bin_transaction_id) VALUES (2, 9)"
            ))


def test_null_linked_ids_still_allowed_after_index():
    """
    The partial indexes only cover non-NULL values. Multiple rows with NULL
    linked ids must still be insertable after upgrade.
    """
    engine = _engine()
    _upgrade(engine)

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items (id, linked_transaction_id) "
            "VALUES (1, NULL), (2, NULL)"
        ))


# ── Downgrade ─────────────────────────────────────────────────────────────────

def test_downgrade_removes_txn_unique_index():
    """After downgrade, duplicate linked_transaction_id rows can be inserted."""
    engine = _engine()
    _upgrade(engine)
    _downgrade(engine)

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items (id, linked_transaction_id) "
            "VALUES (1, 42), (2, 42)"
        ))


def test_downgrade_removes_bin_txn_unique_index():
    """After downgrade, duplicate linked_bin_transaction_id rows can be inserted."""
    engine = _engine()
    _upgrade(engine)
    _downgrade(engine)

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items (id, linked_bin_transaction_id) "
            "VALUES (1, 88), (2, 88)"
        ))


def test_downgrade_is_idempotent():
    """Running downgrade twice must not raise."""
    engine = _engine()
    _upgrade(engine)
    _downgrade(engine)
    _downgrade(engine)  # second downgrade must be a no-op


def test_upgrade_is_idempotent():
    """Running upgrade twice must not raise (IF NOT EXISTS on index creation)."""
    engine = _engine()
    _upgrade(engine)
    _upgrade(engine)


# ── Three-way dedup ───────────────────────────────────────────────────────────

def test_three_duplicates_keeps_best_and_merges():
    """
    Among three duplicates (pending, completed-no-notes, completed-with-notes),
    the best survivor is chosen and state is merged from both discards.
    """
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items "
            "(id, linked_transaction_id, is_completed, completed_at, "
            " completed_by_user_id, completion_notes, photo_requested_via_telegram) "
            "VALUES "
            "(1, 100, 0, NULL, NULL, NULL, 0), "                      # pending
            "(2, 100, 1, '2026-05-01T10:00:00', NULL, NULL, 0), "     # completed, no by/notes
            "(3, 100, 1, '2026-05-01T11:00:00', 8, 'proof', 1)"       # completed, richest data
        ))
    _upgrade(engine)

    rows = _rows(engine, "WHERE linked_transaction_id = 100")
    assert len(rows) == 1
    s = rows[0]
    assert s[0] == 3               # richest completed row wins
    assert s[5] == 8               # completed_by_user_id
    assert s[6] == "proof"         # completion_notes
    assert s[7] in (1, True)       # photo flag


# ── Boolean binding safety (PG regression guard) ──────────────────────────────

def test_photo_flag_merged_from_discard_with_only_photo_set():
    """
    Survivor has photo_requested_via_telegram=False; discard has it True.
    After merge the survivor must have it truthy.  This exercises the boolean
    bind path that previously used integer 1/0 (unsafe on PostgreSQL BOOLEAN).
    The Python bool value (True/False) is what the fixed migration binds.
    """
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items "
            "(id, linked_transaction_id, is_completed, completed_at, "
            " photo_requested_via_telegram) "
            "VALUES "
            "(1, 200, 1, '2026-05-10T10:00:00', 0), "  # completed, photo=False
            "(2, 200, 0, NULL, 1)"                       # pending, photo=True → merged in
        ))
    _upgrade(engine)

    rows = _rows(engine, "WHERE linked_transaction_id = 200")
    assert len(rows) == 1
    s = rows[0]
    assert s[0] == 1               # completed row survived
    assert s[7] in (1, True)       # photo flag was merged from discard


def test_photo_flag_false_on_both_survivor_and_discards_stays_false():
    """When no row in the group has photo_requested_via_telegram set, the
    survivor must keep it falsy after merge."""
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO checklist_items "
            "(id, linked_transaction_id, is_completed, photo_requested_via_telegram) "
            "VALUES "
            "(1, 201, 1, 0), "  # completed, photo=False
            "(2, 201, 0, 0)"    # pending, photo=False
        ))
    _upgrade(engine)

    rows = _rows(engine, "WHERE linked_transaction_id = 201")
    assert len(rows) == 1
    assert rows[0][7] in (0, False)  # photo flag remains falsy
