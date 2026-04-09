"""Add BinTransaction table and bin_transaction_id to transactions

Revision ID: 005
Revises: 004
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # bin_transactions must come before altering transactions (FK dependency)
    op.create_table(
        "bin_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bin_id", sa.Integer(), sa.ForeignKey("bins.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("processed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="CHECKED_OUT"),
        sa.Column("checked_out_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bin_transactions_bin_id", "bin_transactions", ["bin_id"])
    op.create_index("ix_bin_transactions_user_id", "bin_transactions", ["user_id"])
    op.create_index("ix_bin_transactions_status", "bin_transactions", ["status"])

    # Add bin_transaction_id FK to transactions
    op.add_column(
        "transactions",
        sa.Column("bin_transaction_id", sa.Integer(), sa.ForeignKey("bin_transactions.id"), nullable=True),
    )
    op.create_index("ix_transactions_bin_transaction_id", "transactions", ["bin_transaction_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_bin_transaction_id", "transactions")
    op.drop_column("transactions", "bin_transaction_id")
    op.drop_table("bin_transactions")
