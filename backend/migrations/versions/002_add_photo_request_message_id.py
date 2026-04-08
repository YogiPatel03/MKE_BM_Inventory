"""Add photo_request_message_id to transactions

Revision ID: 002
Revises: 001
Create Date: 2026-04-02
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("photo_request_message_id", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "photo_request_message_id")
