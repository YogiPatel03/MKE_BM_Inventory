"""Add subchecklists table and per-task assignee/subchecklist to checklist_items

Revision ID: 014
Revises: 013
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create subchecklists table
    op.create_table(
        "subchecklists",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("checklist_id", sa.Integer, sa.ForeignKey("checklists.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("section_type", sa.String(20), nullable=False, server_default="CUSTOM"),
        sa.Column("is_mandatory", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("section_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_subchecklists_checklist_id", "subchecklists", ["checklist_id"])

    # Add subchecklist_id and assignee_id to checklist_items
    op.add_column(
        "checklist_items",
        sa.Column("subchecklist_id", sa.Integer, sa.ForeignKey("subchecklists.id"), nullable=True),
    )
    op.add_column(
        "checklist_items",
        sa.Column("assignee_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_checklist_items_subchecklist_id", "checklist_items", ["subchecklist_id"])


def downgrade() -> None:
    op.drop_index("ix_checklist_items_subchecklist_id", "checklist_items")
    op.drop_column("checklist_items", "assignee_id")
    op.drop_column("checklist_items", "subchecklist_id")
    op.drop_index("ix_subchecklists_checklist_id", "subchecklists")
    op.drop_table("subchecklists")
