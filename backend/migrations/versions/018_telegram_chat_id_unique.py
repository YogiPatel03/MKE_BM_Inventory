"""Add unique constraint to users.telegram_chat_id

Revision ID: 018
Revises: 017
Create Date: 2026-05-07

ADMIN NOTE: This migration nulls out two categories of telegram_chat_id values before
adding the unique constraint:

1. Negative values (group/supergroup/channel IDs). These come from users who ran /link
   from a group chat before the identity fix. They do not represent individual Telegram
   accounts and may leak DM notifications to group chats.

2. Duplicate positive values (same Telegram user ID on multiple app accounts). For each
   duplicate set the earliest-registered user (lowest id) keeps their value; all others
   are nulled.

Affected users must re-link: go to Settings → Link Telegram, generate a new token,
DM the bot, and run /link <token>.

To audit affected rows before migration, run:
  -- Negative IDs to be nulled:
  SELECT id, username, telegram_chat_id FROM users WHERE telegram_chat_id LIKE '-%';
  -- Duplicate positive IDs to be nulled (non-min-id rows):
  SELECT id, username, telegram_chat_id FROM users
  WHERE telegram_chat_id IS NOT NULL
    AND id NOT IN (SELECT MIN(id) FROM users WHERE telegram_chat_id IS NOT NULL
                   GROUP BY telegram_chat_id)
    AND telegram_chat_id IN (SELECT telegram_chat_id FROM users
                              WHERE telegram_chat_id IS NOT NULL
                              GROUP BY telegram_chat_id HAVING COUNT(*) > 1);
"""
from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Null all negative telegram_chat_id values.
    # Negative Telegram IDs belong to groups, supergroups, and channels — not individual
    # users. Any user whose telegram_chat_id starts with '-' linked from a group before
    # the identity fix and needs to re-link.
    op.execute(sa.text(
        "UPDATE users SET telegram_chat_id = NULL WHERE telegram_chat_id LIKE '-%'"
    ))

    # Step 2: For duplicate positive telegram_chat_id values, keep the earliest-registered
    # user (lowest id) and null all others. Those users must also re-link.
    op.execute(sa.text("""
        UPDATE users SET telegram_chat_id = NULL
        WHERE telegram_chat_id IS NOT NULL
        AND id NOT IN (
            SELECT MIN(id) FROM users
            WHERE telegram_chat_id IS NOT NULL
            GROUP BY telegram_chat_id
        )
        AND telegram_chat_id IN (
            SELECT telegram_chat_id FROM users
            WHERE telegram_chat_id IS NOT NULL
            GROUP BY telegram_chat_id HAVING COUNT(*) > 1
        )
    """))

    op.create_unique_constraint("uq_users_telegram_chat_id", "users", ["telegram_chat_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_telegram_chat_id", "users", type_="unique")
