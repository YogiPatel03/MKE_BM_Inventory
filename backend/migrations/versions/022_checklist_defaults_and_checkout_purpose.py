"""Add checklist_assignment_defaults table and checkout purpose field

Revision ID: 022
Revises: 021
Create Date: 2026-05-19

Changes:
  - New table: checklist_assignment_defaults
      Stores recurring default assignees per group. A partial unique index
      (WHERE is_active) ensures no duplicate active defaults per group/user
      while preserving deactivated history rows.
  - New column: transactions.purpose  (VARCHAR 20, default 'GENERAL')
  - New column: bin_transactions.purpose  (VARCHAR 20, default 'GENERAL')
"""
from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── checklist_assignment_defaults ─────────────────────────────────────────
    op.create_table(
        "checklist_assignment_defaults",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("group_name", sa.String(50), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_checklist_defaults_group_name",
        "checklist_assignment_defaults",
        ["group_name"],
    )
    # Partial unique index: only one active default per (group_name, user_id).
    # Inactive rows are preserved as history and do not participate in the constraint.
    # WHERE is_active works in both SQLite (stored as 0/1) and PostgreSQL (boolean).
    op.execute(
        "CREATE UNIQUE INDEX uq_checklist_defaults_active "
        "ON checklist_assignment_defaults (group_name, user_id) "
        "WHERE is_active"
    )

    # ── purpose column on transactions ────────────────────────────────────────
    op.add_column(
        "transactions",
        sa.Column(
            "purpose",
            sa.String(20),
            nullable=False,
            server_default="GENERAL",
        ),
    )

    # ── purpose column on bin_transactions ───────────────────────────────────
    op.add_column(
        "bin_transactions",
        sa.Column(
            "purpose",
            sa.String(20),
            nullable=False,
            server_default="GENERAL",
        ),
    )


def downgrade() -> None:
    op.drop_column("bin_transactions", "purpose")
    op.drop_column("transactions", "purpose")
    op.execute("DROP INDEX uq_checklist_defaults_active")
    op.drop_index("ix_checklist_defaults_group_name", table_name="checklist_assignment_defaults")
    op.drop_table("checklist_assignment_defaults")
