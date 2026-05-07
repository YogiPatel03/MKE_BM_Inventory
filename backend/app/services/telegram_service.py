"""
Telegram service — sends notifications and manages bot state.

All public notification functions are fire-and-forget: they catch all
exceptions internally, log safe context (IDs only — no tokens or message
bodies), and never raise into callers. This ensures Telegram failures
cannot affect committed business actions.

Topic routing:
  Telegram forum topics share the same supergroup chat_id; each topic has a
  unique message_thread_id. TELEGRAM_GROUP_TOPIC_THREAD_IDS maps group names
  to thread IDs. send_to_group_topic() uses this mapping; if the mapping is
  absent the message falls back to the coordinator chat without a thread.
"""

import html
import json
import logging
from typing import TYPE_CHECKING, Optional

from telegram import Bot
from telegram.error import TelegramError

from app.config import settings
from app.models.transaction import Transaction

if TYPE_CHECKING:
    from app.models.bin_transaction import BinTransaction
    from app.models.checklist import ChecklistItem
    from app.models.user import User

log = logging.getLogger(__name__)

_bot: Optional[Bot] = None


def get_bot() -> Optional[Bot]:
    global _bot
    if not settings.telegram_enabled:
        return None
    if _bot is None:
        _bot = Bot(token=settings.telegram_bot_token)
    return _bot


# ─── Topic mapping helpers ────────────────────────────────────────────────────

def _parse_topic_mapping() -> dict[str, int]:
    """
    Parse TELEGRAM_GROUP_TOPIC_THREAD_IDS from settings.
    Returns an empty dict (and logs a warning) on invalid JSON — never raises.
    """
    raw = (settings.telegram_group_topic_thread_ids or "").strip()
    if not raw:
        return {}
    try:
        mapping = json.loads(raw)
        if not isinstance(mapping, dict):
            log.warning("TELEGRAM_GROUP_TOPIC_THREAD_IDS is not a JSON object — ignoring")
            return {}
        return {str(k): int(v) for k, v in mapping.items()}
    except (json.JSONDecodeError, ValueError, TypeError):
        log.warning(
            "TELEGRAM_GROUP_TOPIC_THREAD_IDS contains invalid JSON — topic routing disabled"
        )
        return {}


def get_thread_id_for_group(group_name: str) -> Optional[int]:
    """Return the message_thread_id for a group, or None if not configured."""
    return _parse_topic_mapping().get(group_name)


def get_group_for_thread_id(message_thread_id: int) -> Optional[str]:
    """Return the group name that maps to this thread ID, or None."""
    for group, tid in _parse_topic_mapping().items():
        if tid == message_thread_id:
            return group
    return None


# ─── Low-level send ───────────────────────────────────────────────────────────

async def _send(chat_id: str, text: str, *, message_thread_id: Optional[int] = None) -> Optional[int]:
    """
    Send a message; return message_id or None on failure. Never raises.
    Pass message_thread_id to route into a forum topic.
    """
    if not chat_id:
        return None
    try:
        bot = get_bot()
        if not bot:
            return None
        kwargs: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if message_thread_id is not None:
            kwargs["message_thread_id"] = message_thread_id
        msg = await bot.send_message(**kwargs)
        return msg.message_id
    except TelegramError as e:
        log.warning("Telegram send failed to %s: %s", chat_id, e)
        return None
    except Exception:
        log.exception("Unexpected error in Telegram send to %s", chat_id)
        return None


async def send_to_group_topic(group_name: str, text: str) -> Optional[int]:
    """
    Send to the coordinator chat, targeting the topic thread for group_name.
    Falls back to the coordinator chat without a thread if no mapping exists.
    Returns message_id or None. Never raises.
    """
    if not settings.telegram_coordinator_chat_id:
        log.warning("send_to_group_topic called but TELEGRAM_COORDINATOR_CHAT_ID is not set")
        return None
    thread_id = get_thread_id_for_group(group_name)
    if thread_id is None:
        log.warning(
            "No topic thread_id configured for group %s — sending to coordinator chat without thread",
            group_name,
        )
    return await _send(settings.telegram_coordinator_chat_id, text, message_thread_id=thread_id)


async def send_user_dm(user: "User", text: str) -> bool:
    """DM a linked user. Returns True on success, False if unlinked or send failed. Never raises."""
    if not user or not user.telegram_chat_id:
        log.debug("Skipping DM for user %s: no Telegram link", getattr(user, "id", "unknown"))
        return False
    try:
        result = await _send(user.telegram_chat_id, text)
        if result is None:
            log.warning("DM failed for user_id=%s", user.id)
        return result is not None
    except Exception:
        log.exception("Unexpected error sending DM to user_id=%s", user.id)
        return False


async def notify_checkout(transaction: Transaction) -> None:
    """Notify coordinator channel and DM the borrower when an item is checked out. Never raises."""
    try:
        tg_handle = transaction.user.telegram_handle
        user_display = html.escape(f"@{tg_handle}" if tg_handle else transaction.user.username)
        item_name = html.escape(transaction.item.name)
        due_str = (
            transaction.due_at.strftime("%b %d, %Y") if transaction.due_at else "no due date"
        )

        if settings.telegram_coordinator_chat_id:
            coord_text = (
                f"📦 <b>Checkout</b> #{transaction.id}\n"
                f"Item: <b>{item_name}</b> × {transaction.quantity}\n"
                f"User: {user_display}\n"
                f"Due: {due_str}"
            )
            await _send(settings.telegram_coordinator_chat_id, coord_text)

        dm_text = (
            f"📦 <b>Checkout confirmed</b>\n"
            f"You checked out <b>{item_name}</b> × {transaction.quantity}\n"
            f"Transaction: #{transaction.id}\n"
            f"Due: {due_str}"
        )
        await send_user_dm(transaction.user, dm_text)
    except Exception:
        log.exception("notify_checkout failed for transaction_id=%s", transaction.id)


async def notify_return_and_request_photo(transaction: Transaction) -> Optional[str]:
    """
    Notify coordinator channel when an item is returned and DM the borrower.
    Returns the message_id of the coordinator notification so it can be stored on the
    transaction — this allows the bot to match a photo reply back to the transaction.
    Never raises; always returns the coordinator message_id even if the borrower DM fails.
    """
    try:
        tg_handle = transaction.user.telegram_handle
        user_display = html.escape(f"@{tg_handle}" if tg_handle else transaction.user.username)
        item_name = html.escape(transaction.item.name)

        message_id = None
        if settings.telegram_coordinator_chat_id:
            coord_text = (
                f"✅ <b>Return logged</b> #{transaction.id}\n"
                f"Item: <b>{item_name}</b> × {transaction.quantity}\n"
                f"Returned by: {user_display}\n\n"
                f"📷 No photo was attached. {user_display}, please reply to this message "
                f"with a condition/return photo for the record."
            )
            message_id = await _send(settings.telegram_coordinator_chat_id, coord_text)

        # Borrower DM is fire-and-forget — must not gate returning the coordinator message_id.
        try:
            dm_text = (
                f"✅ <b>Return logged</b>\n"
                f"Your return of <b>{item_name}</b> × {transaction.quantity} has been recorded."
            )
            await send_user_dm(transaction.user, dm_text)
        except Exception:
            log.exception("Borrower DM failed for transaction_id=%s", transaction.id)

        return str(message_id) if message_id else None
    except Exception:
        log.exception("notify_return_and_request_photo failed for transaction_id=%s", transaction.id)
        return None


async def notify_overdue(transaction: Transaction) -> None:
    """DM the user whose checkout is overdue, and notify the coordinator channel."""
    tg_handle = transaction.user.telegram_handle
    user_display = html.escape(f"@{tg_handle}" if tg_handle else transaction.user.username)
    item_name = html.escape(transaction.item.name)
    due_str = (
        transaction.due_at.strftime("%b %d, %Y") if transaction.due_at else "unknown"
    )

    # DM the user
    if transaction.user.telegram_chat_id:
        dm_text = (
            f"⚠️ <b>Overdue item reminder</b>\n"
            f"You have an overdue checkout: <b>{item_name}</b> × {transaction.quantity}\n"
            f"Was due: {due_str}\n"
            f"Please return it as soon as possible."
        )
        await _send(transaction.user.telegram_chat_id, dm_text)

    # Notify coordinator channel
    if settings.telegram_coordinator_chat_id:
        coord_text = (
            f"⏰ <b>Overdue</b> #{transaction.id}\n"
            f"Item: <b>{item_name}</b> × {transaction.quantity}\n"
            f"User: {user_display}\n"
            f"Due: {due_str}"
        )
        await _send(settings.telegram_coordinator_chat_id, coord_text)


async def notify_bin_checkout(bin_txn: "BinTransaction") -> None:
    """Notify coordinator channel and DM the borrower when a bin is checked out. Never raises."""
    try:
        tg_handle = bin_txn.user.telegram_handle
        user_display = html.escape(f"@{tg_handle}" if tg_handle else bin_txn.user.username)
        bin_label = html.escape(bin_txn.bin.label)
        due_str = (
            bin_txn.due_at.strftime("%b %d, %Y") if bin_txn.due_at else "no due date"
        )

        if settings.telegram_coordinator_chat_id:
            coord_text = (
                f"📦 <b>Bin Checkout</b> #{bin_txn.id}\n"
                f"Bin: <b>{bin_label}</b>\n"
                f"User: {user_display}\n"
                f"Due: {due_str}"
            )
            await _send(settings.telegram_coordinator_chat_id, coord_text)

        dm_text = (
            f"📦 <b>Bin checkout confirmed</b>\n"
            f"You checked out bin <b>{bin_label}</b>\n"
            f"Transaction: #{bin_txn.id}\n"
            f"Due: {due_str}"
        )
        await send_user_dm(bin_txn.user, dm_text)
    except Exception:
        log.exception("notify_bin_checkout failed for bin_txn_id=%s", bin_txn.id)


async def notify_bin_return(bin_txn: "BinTransaction") -> None:
    """Notify coordinator channel and DM the borrower when a bin is returned. Never raises."""
    try:
        tg_handle = bin_txn.user.telegram_handle
        user_display = html.escape(f"@{tg_handle}" if tg_handle else bin_txn.user.username)
        bin_label = html.escape(bin_txn.bin.label)

        if settings.telegram_coordinator_chat_id:
            coord_text = (
                f"✅ <b>Bin Return</b> #{bin_txn.id}\n"
                f"Bin: <b>{bin_label}</b>\n"
                f"Returned by: {user_display}"
            )
            await _send(settings.telegram_coordinator_chat_id, coord_text)

        dm_text = (
            f"✅ <b>Bin return recorded</b>\n"
            f"Your return of bin <b>{bin_label}</b> has been logged.\n"
            f"Transaction: #{bin_txn.id}"
        )
        await send_user_dm(bin_txn.user, dm_text)
    except Exception:
        log.exception("notify_bin_return failed for bin_txn_id=%s", bin_txn.id)


async def notify_account_linked(chat_id: str, full_name: str) -> None:
    text = (
        f"✅ Account linked successfully!\n"
        f"Welcome, <b>{html.escape(full_name)}</b>. You'll now receive inventory notifications here."
    )
    await _send(chat_id, text)


async def notify_new_request(request_id: int, requester_name: str, target_name: str, reason: str | None) -> Optional[str]:
    """Notify coordinator channel of a new pending request. Returns message_id."""
    if not settings.telegram_coordinator_chat_id:
        return None

    reason_text = f"\nReason: {html.escape(reason)}" if reason else ""
    text = (
        f"📋 <b>New Request</b> #{request_id}\n"
        f"From: {html.escape(requester_name)}\n"
        f"Item: <b>{html.escape(target_name)}</b>{reason_text}\n\n"
        f"/approve {request_id}  |  /deny {request_id}"
    )
    message_id = await _send(settings.telegram_coordinator_chat_id, text)
    return str(message_id) if message_id else None


async def notify_low_stock(item_name: str, quantity_available: int, threshold: int, location: str) -> None:
    """Alert coordinator channel when an item crosses into low-stock state."""
    if not settings.telegram_coordinator_chat_id:
        return
    text = (
        f"⚠️ <b>Low stock alert</b>\n"
        f"Item: <b>{html.escape(item_name)}</b>\n"
        f"Remaining: {quantity_available} (threshold: {threshold})\n"
        f"Location: {html.escape(location)}\n\n"
        f"Consider restocking soon."
    )
    await _send(settings.telegram_coordinator_chat_id, text)


async def notify_request_submitted(requester_chat_id: str, item_name: str, request_id: int) -> None:
    """DM the requester confirming their request was submitted and is pending."""
    text = (
        f"📋 <b>Request submitted</b>\n"
        f"Your request #{request_id} for <b>{html.escape(item_name)}</b> "
        f"has been submitted and is pending approval."
    )
    await _send(requester_chat_id, text)


async def notify_request_approved(requester_chat_id: str, item_name: str, request_id: int) -> None:
    """DM the requester when their checkout request is approved."""
    text = (
        f"✅ <b>Request approved!</b>\n"
        f"Your request #{request_id} for <b>{html.escape(item_name)}</b> has been approved and fulfilled.\n"
        f"Please collect the item promptly."
    )
    await _send(requester_chat_id, text)


async def notify_request_denied(requester_chat_id: str, item_name: str, request_id: int, reason: str | None) -> None:
    """DM the requester when their checkout request is denied."""
    reason_text = f"\nReason: {html.escape(reason)}" if reason else ""
    text = (
        f"❌ <b>Request denied</b>\n"
        f"Your request #{request_id} for <b>{html.escape(item_name)}</b> was denied.{reason_text}"
    )
    await _send(requester_chat_id, text)


async def notify_checklist_return_proof(task: "ChecklistItem", completer: "User") -> None:
    """
    Request a return proof photo in the coordinator group chat when a
    checklist return task is completed.
    """
    if not settings.telegram_coordinator_chat_id:
        return

    user_display = html.escape(
        f"@{completer.telegram_handle}" if completer.telegram_handle else completer.full_name
    )
    task_title = html.escape(task.title)
    text = (
        f"📋 <b>Checklist return task completed</b>\n"
        f"Task: <b>{task_title}</b>\n"
        f"Completed by: {user_display}\n\n"
        f"📷 {user_display}, please reply to this message with a photo confirming the return."
    )
    await _send(settings.telegram_coordinator_chat_id, text)


async def notify_out_of_stock(item_name: str, location: str) -> None:
    """Alert coordinator channel when an item hits zero stock."""
    if not settings.telegram_coordinator_chat_id:
        return
    text = (
        f"🔴 <b>Out of stock</b>\n"
        f"Item: <b>{html.escape(item_name)}</b>\n"
        f"Location: {html.escape(location)}\n\n"
        f"Item has been moved to Restock Me. Restock to restore."
    )
    await _send(settings.telegram_coordinator_chat_id, text)


async def notify_purchase_and_request_receipt(
    purchase_id: int,
    item_name: str,
    quantity: int,
    purchaser_name: str,
    purchaser_tg_handle: Optional[str] = None,
    purchaser_chat_id: Optional[str] = None,
) -> Optional[str]:
    """
    Notify coordinator channel of a new purchase and ask for a receipt.
    Also DMs the purchaser directly if their Telegram is linked.
    Returns the coordinator channel message_id (used to match photo replies).
    """
    user_display = html.escape(f"@{purchaser_tg_handle}" if purchaser_tg_handle else purchaser_name)
    escaped_item = html.escape(item_name)

    group_text = (
        f"🛒 <b>Purchase logged</b> #{purchase_id}\n"
        f"Item: <b>{escaped_item}</b> × {quantity}\n"
        f"By: {user_display}\n\n"
        f"📄 {user_display}, please reply to this message with a receipt photo or scan."
    )

    message_id: Optional[int] = None
    if settings.telegram_coordinator_chat_id:
        message_id = await _send(settings.telegram_coordinator_chat_id, group_text)

    # DM the purchaser so they don't miss the receipt request
    if purchaser_chat_id:
        dm_text = (
            f"🛒 You just logged a purchase of <b>{escaped_item}</b> × {quantity} (#{purchase_id}).\n\n"
            f"📄 Please reply to the coordinator channel message with a receipt photo or scan."
        )
        await _send(purchaser_chat_id, dm_text)

    return str(message_id) if message_id else None
