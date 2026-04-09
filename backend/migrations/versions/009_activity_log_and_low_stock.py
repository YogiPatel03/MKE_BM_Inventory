"""Add activity_log, low-stock threshold, usage reversal, Restock Me fields

Revision ID: 009
Revises: 008
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── activity_log ──────────────────────────────────────────────────────────
    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("activity_type", sa.String(50), nullable=False),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("target_item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=True),
        sa.Column("target_bin_id", sa.Integer, sa.ForeignKey("bins.id"), nullable=True),
        sa.Column("target_cabinet_id", sa.Integer, sa.ForeignKey("cabinets.id"), nullable=True),
        sa.Column("target_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("quantity_delta", sa.Integer, nullable=True),
        sa.Column("cost_impact", sa.Numeric(10, 2), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column("source_type", sa.String(50), nullable=True),
        sa.Column("source_id", sa.Integer, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_activity_log_activity_type", "activity_log", ["activity_type"])
    op.create_index("ix_activity_log_actor_id", "activity_log", ["actor_id"])
    op.create_index("ix_activity_log_target_item_id", "activity_log", ["target_item_id"])
    op.create_index("ix_activity_log_occurred_at", "activity_log", ["occurred_at"])

    # ── items: low-stock threshold + Restock Me prior location ────────────────
    op.add_column("items", sa.Column("low_stock_threshold", sa.Integer, nullable=True))
    op.add_column("items", sa.Column("prior_cabinet_id", sa.Integer, sa.ForeignKey("cabinets.id"), nullable=True))
    op.add_column("items", sa.Column("prior_bin_id", sa.Integer, sa.ForeignKey("bins.id"), nullable=True))

    # ── usage_events: reversal support ────────────────────────────────────────
    op.add_column("usage_events", sa.Column("is_reversal", sa.Boolean, nullable=False, server_default="0"))
    op.add_column("usage_events", sa.Column("reverses_event_id", sa.Integer, sa.ForeignKey("usage_events.id"), nullable=True))

    # ── location_change_logs: system moves (nullable moved_by) + reason ───────
    op.alter_column("location_change_logs", "moved_by_user_id", nullable=True)
    op.add_column("location_change_logs", sa.Column("move_reason", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("location_change_logs", "move_reason")
    op.alter_column("location_change_logs", "moved_by_user_id", nullable=False)
    op.drop_column("usage_events", "reverses_event_id")
    op.drop_column("usage_events", "is_reversal")
    op.drop_column("items", "prior_bin_id")
    op.drop_column("items", "prior_cabinet_id")
    op.drop_column("items", "low_stock_threshold")
    op.drop_index("ix_activity_log_occurred_at", "activity_log")
    op.drop_index("ix_activity_log_target_item_id", "activity_log")
    op.drop_index("ix_activity_log_actor_id", "activity_log")
    op.drop_index("ix_activity_log_activity_type", "activity_log")
    op.drop_table("activity_log")
