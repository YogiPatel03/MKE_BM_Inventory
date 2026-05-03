"""Migrate quantity fields from Integer to Numeric(10,2) for decimal support

Revision ID: 012
Revises: 011
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # items: quantity_total, quantity_available, low_stock_threshold
    op.alter_column(
        "items", "quantity_total",
        type_=sa.Numeric(10, 2),
        existing_type=sa.Integer(),
        postgresql_using="quantity_total::NUMERIC(10,2)",
    )
    op.alter_column(
        "items", "quantity_available",
        type_=sa.Numeric(10, 2),
        existing_type=sa.Integer(),
        postgresql_using="quantity_available::NUMERIC(10,2)",
    )
    op.alter_column(
        "items", "low_stock_threshold",
        type_=sa.Numeric(10, 2),
        existing_type=sa.Integer(),
        nullable=True,
        postgresql_using="low_stock_threshold::NUMERIC(10,2)",
    )

    # transactions: quantity
    op.alter_column(
        "transactions", "quantity",
        type_=sa.Numeric(10, 2),
        existing_type=sa.Integer(),
        postgresql_using="quantity::NUMERIC(10,2)",
    )

    # usage_events: quantity_used
    op.alter_column(
        "usage_events", "quantity_used",
        type_=sa.Numeric(10, 2),
        existing_type=sa.Integer(),
        postgresql_using="quantity_used::NUMERIC(10,2)",
    )

    # stock_adjustments: delta, quantity_before, quantity_after
    op.alter_column(
        "stock_adjustments", "delta",
        type_=sa.Numeric(10, 2),
        existing_type=sa.Integer(),
        postgresql_using="delta::NUMERIC(10,2)",
    )
    op.alter_column(
        "stock_adjustments", "quantity_before",
        type_=sa.Numeric(10, 2),
        existing_type=sa.Integer(),
        postgresql_using="quantity_before::NUMERIC(10,2)",
    )
    op.alter_column(
        "stock_adjustments", "quantity_after",
        type_=sa.Numeric(10, 2),
        existing_type=sa.Integer(),
        postgresql_using="quantity_after::NUMERIC(10,2)",
    )

    # inventory_requests: quantity_requested
    op.alter_column(
        "inventory_requests", "quantity_requested",
        type_=sa.Numeric(10, 2),
        existing_type=sa.Integer(),
        postgresql_using="quantity_requested::NUMERIC(10,2)",
    )


def downgrade() -> None:
    op.alter_column(
        "inventory_requests", "quantity_requested",
        type_=sa.Integer(),
        existing_type=sa.Numeric(10, 2),
        postgresql_using="quantity_requested::INTEGER",
    )
    op.alter_column(
        "stock_adjustments", "quantity_after",
        type_=sa.Integer(),
        existing_type=sa.Numeric(10, 2),
        postgresql_using="quantity_after::INTEGER",
    )
    op.alter_column(
        "stock_adjustments", "quantity_before",
        type_=sa.Integer(),
        existing_type=sa.Numeric(10, 2),
        postgresql_using="quantity_before::INTEGER",
    )
    op.alter_column(
        "stock_adjustments", "delta",
        type_=sa.Integer(),
        existing_type=sa.Numeric(10, 2),
        postgresql_using="delta::INTEGER",
    )
    op.alter_column(
        "usage_events", "quantity_used",
        type_=sa.Integer(),
        existing_type=sa.Numeric(10, 2),
        postgresql_using="quantity_used::INTEGER",
    )
    op.alter_column(
        "transactions", "quantity",
        type_=sa.Integer(),
        existing_type=sa.Numeric(10, 2),
        postgresql_using="quantity::INTEGER",
    )
    op.alter_column(
        "items", "low_stock_threshold",
        type_=sa.Integer(),
        existing_type=sa.Numeric(10, 2),
        nullable=True,
        postgresql_using="low_stock_threshold::INTEGER",
    )
    op.alter_column(
        "items", "quantity_available",
        type_=sa.Integer(),
        existing_type=sa.Numeric(10, 2),
        postgresql_using="quantity_available::INTEGER",
    )
    op.alter_column(
        "items", "quantity_total",
        type_=sa.Integer(),
        existing_type=sa.Numeric(10, 2),
        postgresql_using="quantity_total::INTEGER",
    )
