"""Add unique partial indexes on checklist_items linked transaction IDs

Revision ID: 024
Revises: 023
Create Date: 2026-05-20

Changes:
  - Deduplicate checklist_items rows before creating the unique indexes.
    For each group sharing a linked_transaction_id or linked_bin_transaction_id,
    keep the single "best" row based on business state:
      1. Prefer completed rows (is_completed=True) over pending.
      2. Among completed rows, prefer those with the richest completion data
         (completed_at, completed_by_user_id, completion_notes,
          photo_requested_via_telegram).
      3. Fall back to lowest id as final tiebreaker.
    Before deleting the discarded rows, merge their completion state into the
    survivor (filling only fields that are NULL/False on the survivor).
  - Add unique partial index uq_checklist_item_linked_txn (IF NOT EXISTS).
  - Add unique partial index uq_checklist_item_linked_bin_txn (IF NOT EXISTS).

Safety notes:
  - All rows sharing a linked id are included in the dedupe, regardless of
    auto_type, so no business data is silently dropped.
  - IF NOT EXISTS prevents failures when the model-level Index already exists
    on databases created via Base.metadata.create_all().
  - Works on SQLite and PostgreSQL (partial index WHERE syntax is portable).
"""
from alembic import op
from sqlalchemy import text

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def _score(is_completed, completed_at, completed_by_user_id, completion_notes,
           photo_requested_via_telegram, row_id):
    """Return a sort key; lower value = preferred survivor."""
    return (
        (0 if is_completed else 1) * 10_000_000
        + (0 if completed_at else 1) * 1_000_000
        + (0 if completed_by_user_id else 1) * 100_000
        + (0 if completion_notes else 1) * 10_000
        + (0 if photo_requested_via_telegram else 1) * 1_000
        + row_id  # tiebreaker: prefer lower id
    )


def _dedup_field(bind, field: str) -> None:
    """
    Dedup checklist_items rows that share the same non-NULL value for `field`.

    All rows in a duplicate group are considered regardless of auto_type, so
    unexpected business data is never silently dropped — the completion state
    of every discarded row is merged into the survivor before deletion.
    """
    dup_ids = bind.execute(text(
        f"SELECT {field} FROM checklist_items "
        f"WHERE {field} IS NOT NULL "
        f"GROUP BY {field} HAVING COUNT(*) > 1"
    )).fetchall()

    for (linked_id,) in dup_ids:
        rows = bind.execute(text(
            "SELECT id, is_completed, completed_at, completed_by_user_id, "
            "completion_notes, photo_requested_via_telegram, auto_type "
            f"FROM checklist_items WHERE {field} = :lid"
        ), {"lid": linked_id}).fetchall()

        if len(rows) <= 1:
            continue

        scored = sorted(
            rows,
            key=lambda r: _score(r[1], r[2], r[3], r[4], r[5], r[0]),
        )
        survivor = scored[0]
        discarded = scored[1:]

        # Accumulate the best available values from discarded rows for any
        # fields the survivor currently has as NULL/False.
        s_completed_at = survivor[2]
        s_completed_by = survivor[3]
        s_notes = survivor[4]
        s_photo = bool(survivor[5])

        for d in discarded:
            if not s_completed_at and d[2]:
                s_completed_at = d[2]
            if not s_completed_by and d[3]:
                s_completed_by = d[3]
            if not s_notes and d[4]:
                s_notes = d[4]
            if not s_photo and d[5]:
                s_photo = True

        bind.execute(text(
            "UPDATE checklist_items SET "
            "  completed_at = :cat, "
            "  completed_by_user_id = :cby, "
            "  completion_notes = :notes, "
            "  photo_requested_via_telegram = :photo "
            "WHERE id = :sid"
        ), {
            "cat": s_completed_at,
            "cby": s_completed_by,
            "notes": s_notes,
            "photo": s_photo,  # Python bool: SQLAlchemy maps to BOOLEAN on PG, INTEGER on SQLite
            "sid": survivor[0],
        })

        for d in discarded:
            bind.execute(text("DELETE FROM checklist_items WHERE id = :id"), {"id": d[0]})


def upgrade() -> None:
    bind = op.get_bind()

    _dedup_field(bind, "linked_transaction_id")
    _dedup_field(bind, "linked_bin_transaction_id")

    # IF NOT EXISTS handles databases already created via Base.metadata.create_all().
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_checklist_item_linked_txn "
        "ON checklist_items (linked_transaction_id) "
        "WHERE linked_transaction_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_checklist_item_linked_bin_txn "
        "ON checklist_items (linked_bin_transaction_id) "
        "WHERE linked_bin_transaction_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_checklist_item_linked_bin_txn")
    op.execute("DROP INDEX IF EXISTS uq_checklist_item_linked_txn")
