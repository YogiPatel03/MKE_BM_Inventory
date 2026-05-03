"""Change activity_log.quantity_delta from Integer to Numeric(10,2)

Revision ID: 015
Revises: 014
Create Date: 2026-05-02
"""
from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "activity_log",
        "quantity_delta",
        type_=sa.Numeric(10, 2),
        existing_type=sa.Integer(),
        postgresql_using="quantity_delta::NUMERIC(10, 2)",
    )


def downgrade() -> None:
    op.alter_column(
        "activity_log",
        "quantity_delta",
        type_=sa.Integer(),
        existing_type=sa.Numeric(10, 2),
        postgresql_using="quantity_delta::INTEGER",
    )
