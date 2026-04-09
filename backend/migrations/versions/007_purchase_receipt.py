"""Add PurchaseRecord and ReceiptRecord tables

Revision ID: 007
Revises: 006
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # receipt_records first (purchase_records FK depends on it)
    op.create_table(
        "receipt_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("vendor", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("uploaded_via", sa.String(20), nullable=False, server_default="web"),
        sa.Column("telegram_request_message_id", sa.String(100), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_receipt_records_uploaded_by_user_id", "receipt_records", ["uploaded_by_user_id"])

    # purchase_records
    op.create_table(
        "purchase_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("purchased_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("receipt_id", sa.Integer(), sa.ForeignKey("receipt_records.id"), nullable=True),
        sa.Column("quantity_purchased", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("total_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("vendor", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("purchased_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_purchase_records_item_id", "purchase_records", ["item_id"])
    op.create_index("ix_purchase_records_purchased_by_user_id", "purchase_records", ["purchased_by_user_id"])


def downgrade() -> None:
    op.drop_table("purchase_records")
    op.drop_table("receipt_records")
