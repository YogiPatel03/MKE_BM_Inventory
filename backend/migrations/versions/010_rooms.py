"""Add rooms table, room_id to cabinets, group_name to users

Revision ID: 010
Revises: 009
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── rooms table ──────────────────────────────────────────────────────────
    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── room_id on cabinets (nullable first for backfill) ─────────────────────
    op.add_column(
        "cabinets",
        sa.Column("room_id", sa.Integer, sa.ForeignKey("rooms.id"), nullable=True),
    )
    op.create_index("ix_cabinets_room_id", "cabinets", ["room_id"])

    # ── Seed default room and migrate existing cabinets ───────────────────────
    op.execute(
        "INSERT INTO rooms (name, description) VALUES "
        "('Shishu Mandal', 'Default room for existing cabinets')"
    )
    op.execute(
        "UPDATE cabinets SET room_id = (SELECT id FROM rooms WHERE name = 'Shishu Mandal' LIMIT 1)"
    )

    # ── Make room_id NOT NULL after backfill ──────────────────────────────────
    op.alter_column("cabinets", "room_id", nullable=False)

    # ── group_name on users ───────────────────────────────────────────────────
    op.add_column(
        "users",
        sa.Column("group_name", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "group_name")
    op.drop_index("ix_cabinets_room_id", "cabinets")
    op.drop_column("cabinets", "room_id")
    op.drop_table("rooms")
