"""Add included_item_ids to bin_transactions for partial bin checkout tracking

Revision ID: 013
Revises: 012
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add included_item_ids JSON column to bin_transactions.
    # Stores the list of item IDs that were physically included in the bin checkout.
    # Items already individually checked out at time of bin checkout are excluded.
    op.add_column(
        "bin_transactions",
        sa.Column("included_item_ids", sa.JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bin_transactions", "included_item_ids")
