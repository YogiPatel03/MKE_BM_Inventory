"""Add UsageEvent, StockAdjustment, LocationChangeLog tables

Revision ID: 004
Revises: 003
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # usage_events
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("processed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("quantity_used", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # stock_adjustments
    op.create_table(
        "stock_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("adjusted_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("quantity_before", sa.Integer(), nullable=False),
        sa.Column("quantity_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(50), nullable=False, server_default="CORRECTION"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("adjusted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # location_change_logs
    op.create_table(
        "location_change_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_type", sa.String(10), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("moved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("from_cabinet_id", sa.Integer(), sa.ForeignKey("cabinets.id"), nullable=True),
        sa.Column("to_cabinet_id", sa.Integer(), sa.ForeignKey("cabinets.id"), nullable=True),
        sa.Column("from_bin_id", sa.Integer(), sa.ForeignKey("bins.id"), nullable=True),
        sa.Column("to_bin_id", sa.Integer(), sa.ForeignKey("bins.id"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("moved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("location_change_logs")
    op.drop_table("stock_adjustments")
    op.drop_table("usage_events")
