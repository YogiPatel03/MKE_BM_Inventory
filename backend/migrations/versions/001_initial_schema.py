"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Roles
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("can_manage_inventory", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("can_manage_cabinets", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("can_manage_bins", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("can_manage_users", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("can_process_any_transaction", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("can_view_all_transactions", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("can_view_audit_logs", sa.Boolean, nullable=False, server_default="false"),
    )

    # Seed roles
    op.execute("""
        INSERT INTO roles (name, can_manage_inventory, can_manage_cabinets, can_manage_bins,
            can_manage_users, can_process_any_transaction, can_view_all_transactions, can_view_audit_logs)
        VALUES
            ('ADMIN',       true,  true,  true,  true,  true,  true,  true),
            ('COORDINATOR', true,  true,  true,  false, true,  true,  true),
            ('GROUP_LEAD',  false, false, false, false, true,  true,  true),
            ('USER',        false, false, false, false, false, false, false)
    """)

    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("telegram_handle", sa.String(100), nullable=True),
        sa.Column("telegram_chat_id", sa.String(100), nullable=True),
        sa.Column("telegram_link_token", sa.String(64), nullable=True, unique=True),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"])

    # Cabinets
    op.create_table(
        "cabinets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Bins
    op.create_table(
        "bins",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cabinet_id", sa.Integer, sa.ForeignKey("cabinets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("group_number", sa.Integer, nullable=True),
        sa.Column("location_note", sa.String(500), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bins_cabinet_id", "bins", ["cabinet_id"])

    # Items
    op.create_table(
        "items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("quantity_total", sa.Integer, nullable=False, server_default="1"),
        sa.Column("quantity_available", sa.Integer, nullable=False, server_default="1"),
        sa.Column("cabinet_id", sa.Integer, sa.ForeignKey("cabinets.id"), nullable=False),
        sa.Column("bin_id", sa.Integer, sa.ForeignKey("bins.id"), nullable=True),
        sa.Column("sku", sa.String(100), nullable=True, unique=True),
        sa.Column("condition", sa.String(20), nullable=False, server_default="'GOOD'"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity_available >= 0", name="ck_item_qty_available_non_negative"),
        sa.CheckConstraint("quantity_total >= 0", name="ck_item_qty_total_non_negative"),
        sa.CheckConstraint("quantity_available <= quantity_total", name="ck_item_qty_available_lte_total"),
    )
    op.create_index("ix_items_name", "items", ["name"])
    op.create_index("ix_items_cabinet_id", "items", ["cabinet_id"])

    # Transactions
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("processed_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="'CHECKED_OUT'"),
        sa.Column("checked_out_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("photo_requested_via_telegram", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_transaction_qty_positive"),
    )
    op.create_index("ix_transactions_item_id", "transactions", ["item_id"])
    op.create_index("ix_transactions_user_id", "transactions", ["user_id"])
    op.create_index("ix_transactions_status", "transactions", ["status"])

    # Transaction photos
    op.create_table(
        "transaction_photos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("transaction_id", sa.Integer, sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("telegram_message_id", sa.String(100), nullable=True),
        sa.Column("telegram_file_id", sa.String(500), nullable=True),
        sa.Column("telegram_chat_id", sa.String(100), nullable=True),
        sa.Column("caption", sa.Text, nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_transaction_photos_transaction_id", "transaction_photos", ["transaction_id"])


def downgrade() -> None:
    op.drop_table("transaction_photos")
    op.drop_table("transactions")
    op.drop_table("items")
    op.drop_table("bins")
    op.drop_table("cabinets")
    op.drop_table("users")
    op.drop_table("roles")
