"""Add InventoryRequest table

Revision ID: 006
Revises: 005
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inventory_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requester_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approver_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=True),
        sa.Column("bin_id", sa.Integer(), sa.ForeignKey("bins.id"), nullable=True),
        sa.Column("quantity_requested", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("denial_reason", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telegram_message_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inventory_requests_requester_id", "inventory_requests", ["requester_id"])
    op.create_index("ix_inventory_requests_approver_id", "inventory_requests", ["approver_id"])
    op.create_index("ix_inventory_requests_item_id", "inventory_requests", ["item_id"])
    op.create_index("ix_inventory_requests_bin_id", "inventory_requests", ["bin_id"])
    op.create_index("ix_inventory_requests_status", "inventory_requests", ["status"])


def downgrade() -> None:
    op.drop_table("inventory_requests")
