"""Change purchase_records.quantity_purchased from Integer to Numeric(10,2)

Revision ID: 017
Revises: 016
Create Date: 2026-05-02
"""
from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "purchase_records",
        "quantity_purchased",
        type_=sa.Numeric(10, 2),
        existing_type=sa.Integer(),
        postgresql_using="quantity_purchased::NUMERIC(10, 2)",
    )


def downgrade() -> None:
    op.alter_column(
        "purchase_records",
        "quantity_purchased",
        type_=sa.Integer(),
        existing_type=sa.Numeric(10, 2),
        postgresql_using="quantity_purchased::INTEGER",
    )
