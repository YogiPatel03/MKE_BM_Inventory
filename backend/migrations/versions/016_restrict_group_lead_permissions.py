"""Restrict GROUP_LEAD permissions: remove global transaction/audit access

Revision ID: 016
Revises: 015
Create Date: 2026-05-02
"""
from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE roles
        SET can_process_any_transaction = false,
            can_view_all_transactions   = false,
            can_view_audit_logs         = false
        WHERE name = 'GROUP_LEAD'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE roles
        SET can_process_any_transaction = true,
            can_view_all_transactions   = true,
            can_view_audit_logs         = true
        WHERE name = 'GROUP_LEAD'
    """)
