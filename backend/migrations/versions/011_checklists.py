"""Add checklists, checklist_items, checklist_assignments tables

Revision ID: 011
Revises: 010
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── checklists ────────────────────────────────────────────────────────────
    op.create_table(
        "checklists",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("group_name", sa.String(50), nullable=False),
        sa.Column("week_start", sa.Date, nullable=False),  # Always Monday
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_checklists_group_name", "checklists", ["group_name"])
    op.create_index("ix_checklists_week_start", "checklists", ["week_start"])
    # Unique: one checklist per group per week
    op.create_unique_constraint(
        "uq_checklists_group_week", "checklists", ["group_name", "week_start"]
    )

    # ── checklist_items ───────────────────────────────────────────────────────
    op.create_table(
        "checklist_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("checklist_id", sa.Integer, sa.ForeignKey("checklists.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("item_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_auto_generated", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("auto_type", sa.String(20), nullable=True),
        sa.Column("linked_transaction_id", sa.Integer,
                  sa.ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_bin_transaction_id", sa.Integer,
                  sa.ForeignKey("bin_transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_completed", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("completion_notes", sa.Text, nullable=True),
        sa.Column("photo_requested_via_telegram", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_checklist_items_checklist_id", "checklist_items", ["checklist_id"])

    # ── checklist_assignments ─────────────────────────────────────────────────
    op.create_table(
        "checklist_assignments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("checklist_id", sa.Integer, sa.ForeignKey("checklists.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_checklist_assignments_checklist_id", "checklist_assignments", ["checklist_id"])
    op.create_index("ix_checklist_assignments_user_id", "checklist_assignments", ["user_id"])
    op.create_unique_constraint(
        "uq_checklist_assignments_user", "checklist_assignments", ["checklist_id", "user_id"]
    )


def downgrade() -> None:
    op.drop_table("checklist_assignments")
    op.drop_table("checklist_items")
    op.drop_table("checklists")
