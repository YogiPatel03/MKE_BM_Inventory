"""Add requires_full_bin_checkout to bins

Revision ID: 019
Revises: 018
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bins",
        sa.Column(
            "requires_full_bin_checkout",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("bins", "requires_full_bin_checkout")
