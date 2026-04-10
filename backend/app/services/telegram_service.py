"""
Telegram service — sends notifications and manages bot state.

All Telegram calls are fire-and-forget; failures are logged but never
raise exceptions to callers. The bot's coordinator channel is the primary
notification target; user DMs are used for overdue reminders when a
telegram_chat_id is linked.
"""

import logging
from typing import TYPE_CHECKING, Optional

from telegram import Bot
from telegram.error import TelegramError

from app.config import settings
from app.models.transaction import Transaction

if TYPE_CHECKING:
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


async def _send(chat_id: str, text: str) -> Optional[int]:
    """Send a message; return message_id or None on failure."""
    bot = get_bot()
    if not bot or not chat_id:
        return None
    try:
        msg = await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        return msg.message_id
    except TelegramError as e:
        log.warning("Telegram send failed to %s: %s", chat_id, e)
        return None


async def notify_checkout(transaction: Transaction) -> None:
    """Notify coordinator channel when an item is checked out."""
    if not settings.telegram_coordinator_chat_id:
        return

    username = transaction.user.username
    tg_handle = transaction.user.telegram_handle
    user_display = f"@{tg_handle}" if tg_handle else username

    item_name = transaction.item.name
    due_str = (
        transaction.due_at.strftime("%b %d, %Y") if transaction.due_at else "no due date"
    )

    text = (
        f"📦 <b>Checkout</b> #{transaction.id}\n"
        f"Item: <b>{item_name}</b> × {transaction.quantity}\n"
        f"User: {user_display}\n"
        f"Due: {due_str}"
    )
    await _send(settings.telegram_coordinator_chat_id, text)


async def notify_return_and_request_photo(transaction: Transaction) -> Optional[str]:
    """
    Notify coordinator channel when an item is returned.
    Returns the message_id of the sent notification so it can be stored on the
    transaction — this allows the bot to match a photo reply back to the transaction.
    """
    if not settings.telegram_coordinator_chat_id:
        return None

    username = transaction.user.username
    tg_handle = transaction.user.telegram_handle
    user_display = f"@{tg_handle}" if tg_handle else username
    item_name = transaction.item.name

    text = (
        f"✅ <b>Return logged</b> #{transaction.id}\n"
        f"Item: <b>{item_name}</b> × {transaction.quantity}\n"
        f"Returned by: {user_display}\n\n"
        f"📷 No photo was attached. {user_display}, please reply to this message "
        f"with a condition/return photo for the record."
    )
    message_id = await _send(settings.telegram_coordinator_chat_id, text)
    return str(message_id) if message_id else None


async def notify_overdue(transaction: Transaction) -> None:
    """DM the user whose checkout is overdue, and notify the coordinator channel."""
    username = transaction.user.username
    tg_handle = transaction.user.telegram_handle
    user_display = f"@{tg_handle}" if tg_handle else username
    item_name = transaction.item.name
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


async def notify_account_linked(chat_id: str, full_name: str) -> None:
    text = (
        f"✅ Account linked successfully!\n"
        f"Welcome, <b>{full_name}</b>. You'll now receive inventory notifications here."
    )
    await _send(chat_id, text)


async def notify_new_request(request_id: int, requester_name: str, target_name: str, reason: str | None) -> Optional[str]:
    """Notify coordinator channel of a new pending request. Returns message_id."""
    if not settings.telegram_coordinator_chat_id:
        return None

    reason_text = f"\nReason: {reason}" if reason else ""
    text = (
        f"📋 <b>New Request</b> #{request_id}\n"
        f"From: {requester_name}\n"
        f"Item: <b>{target_name}</b>{reason_text}\n\n"
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
        f"Item: <b>{item_name}</b>\n"
        f"Remaining: {quantity_available} (threshold: {threshold})\n"
        f"Location: {location}\n\n"
        f"Consider restocking soon."
    )
    await _send(settings.telegram_coordinator_chat_id, text)


async def notify_request_approved(requester_chat_id: str, item_name: str, request_id: int) -> None:
    """DM the requester when their checkout request is approved."""
    text = (
        f"✅ <b>Request approved!</b>\n"
        f"Your request #{request_id} for <b>{item_name}</b> has been approved and fulfilled.\n"
        f"Please collect the item promptly."
    )
    await _send(requester_chat_id, text)


async def notify_request_denied(requester_chat_id: str, item_name: str, request_id: int, reason: str | None) -> None:
    """DM the requester when their checkout request is denied."""
    reason_text = f"\nReason: {reason}" if reason else ""
    text = (
        f"❌ <b>Request denied</b>\n"
        f"Your request #{request_id} for <b>{item_name}</b> was denied.{reason_text}"
    )
    await _send(requester_chat_id, text)


async def notify_checklist_return_proof(task: "ChecklistItem", completer: "User") -> None:
    """
    Request a return proof photo in the coordinator group chat when a
    checklist return task is completed.
    """
    if not settings.telegram_coordinator_chat_id:
        return

    user_display = f"@{completer.telegram_handle}" if completer.telegram_handle else completer.full_name
    text = (
        f"📋 <b>Checklist return task completed</b>\n"
        f"Task: <b>{task.title}</b>\n"
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
        f"Item: <b>{item_name}</b>\n"
        f"Location: {location}\n\n"
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
    user_display = f"@{purchaser_tg_handle}" if purchaser_tg_handle else purchaser_name

    group_text = (
        f"🛒 <b>Purchase logged</b> #{purchase_id}\n"
        f"Item: <b>{item_name}</b> × {quantity}\n"
        f"By: {user_display}\n\n"
        f"📄 {user_display}, please reply to this message with a receipt photo or scan."
    )

    message_id: Optional[int] = None
    if settings.telegram_coordinator_chat_id:
        message_id = await _send(settings.telegram_coordinator_chat_id, group_text)

    # DM the purchaser so they don't miss the receipt request
    if purchaser_chat_id:
        dm_text = (
            f"🛒 You just logged a purchase of <b>{item_name}</b> × {quantity} (#{purchase_id}).\n\n"
            f"📄 Please reply to the coordinator channel message with a receipt photo or scan."
        )
        await _send(purchaser_chat_id, dm_text)

    return str(message_id) if message_id else None
