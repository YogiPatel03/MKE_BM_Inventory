"""Extend items and bins: is_consumable, unit_price, qr_code_token

Revision ID: 003
Revises: 002
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Items: add is_consumable, unit_price, qr_code_token
    op.add_column("items", sa.Column("is_consumable", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("items", sa.Column("unit_price", sa.Numeric(10, 2), nullable=True))
    op.add_column("items", sa.Column("qr_code_token", sa.String(36), nullable=True))
    op.create_unique_constraint("uq_items_qr_code_token", "items", ["qr_code_token"])
    op.create_index("ix_items_qr_code_token", "items", ["qr_code_token"])

    # Bins: add qr_code_token
    op.add_column("bins", sa.Column("qr_code_token", sa.String(36), nullable=True))
    op.create_unique_constraint("uq_bins_qr_code_token", "bins", ["qr_code_token"])
    op.create_index("ix_bins_qr_code_token", "bins", ["qr_code_token"])

    # Roles: add can_approve_requests
    op.add_column("roles", sa.Column("can_approve_requests", sa.Boolean(), nullable=False, server_default="false"))

    # Seed can_approve_requests for existing roles
    op.execute("""
        UPDATE roles SET can_approve_requests = TRUE
        WHERE name IN ('ADMIN', 'COORDINATOR', 'GROUP_LEAD')
    """)


def downgrade() -> None:
    op.drop_index("ix_items_qr_code_token", "items")
    op.drop_constraint("uq_items_qr_code_token", "items")
    op.drop_column("items", "qr_code_token")
    op.drop_column("items", "unit_price")
    op.drop_column("items", "is_consumable")

    op.drop_index("ix_bins_qr_code_token", "bins")
    op.drop_constraint("uq_bins_qr_code_token", "bins")
    op.drop_column("bins", "qr_code_token")

    op.drop_column("roles", "can_approve_requests")
