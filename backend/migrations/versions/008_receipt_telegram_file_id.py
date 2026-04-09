"""Add telegram_file_id to receipt_records

Revision ID: 008
Revises: 007
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "receipt_records",
        sa.Column("telegram_file_id", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("receipt_records", "telegram_file_id")
