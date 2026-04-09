"""
Telegram bot command handlers.

Routing: the webhook endpoint calls handle_update(), which dispatches to
the appropriate command handler based on the message text.

Account linking flow:
  1. User clicks "Link Telegram" in web app → gets a one-time token
  2. User sends /link <token> to the bot
  3. Bot matches token to User.telegram_link_token, sets telegram_chat_id, clears token
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.transaction import Transaction, TransactionStatus
from app.models.transaction_photo import TransactionPhoto
from app.models.user import User
from app.services.telegram_service import get_bot, notify_account_linked

log = logging.getLogger(__name__)


async def handle_update(body: dict[str, Any], db: AsyncSession) -> None:
    message = body.get("message") or body.get("edited_message")
    if not message:
        return

    chat_id = str(message["chat"]["id"])
    text: str = message.get("text", "")

    # Photo reply: record condition photo for a return
    if message.get("photo") and message.get("reply_to_message"):
        await handle_photo_reply(message, chat_id, db)
        return

    if not text.startswith("/"):
        return

    parts = text.split()
    command = parts[0].lower().split("@")[0]  # strip @BotName suffix

    if command == "/start":
        await cmd_start(chat_id)
    elif command == "/link" and len(parts) == 2:
        await cmd_link(chat_id, parts[1], db)
    elif command == "/myitems":
        await cmd_my_items(chat_id, db)
    elif command == "/overdue":
        await cmd_overdue(chat_id, db)
    elif command == "/status" and len(parts) >= 2:
        item_query = " ".join(parts[1:])
        await cmd_item_status(chat_id, item_query, db)
    elif command == "/requests":
        await cmd_requests(chat_id, db)
    elif command == "/approve" and len(parts) == 2:
        await cmd_approve(chat_id, parts[1], db)
    elif command == "/deny" and len(parts) >= 2:
        reason = " ".join(parts[2:]) if len(parts) > 2 else None
        await cmd_deny(chat_id, parts[1], reason, db)
    else:
        await _send(
            chat_id,
            "Unknown command. Try /start, /myitems, /overdue, /status <item>, /requests, "
            "/approve <id>, /deny <id> [reason]",
        )


async def handle_photo_reply(message: dict[str, Any], chat_id: str, db: AsyncSession) -> None:
    """
    Records a condition photo when someone replies to the bot's photo-request message.
    Matches the reply_to_message.message_id against Transaction.photo_request_message_id.
    """
    reply_to = message["reply_to_message"]
    reply_message_id = str(reply_to.get("message_id", ""))

    if not reply_message_id:
        return

    # Only process replies in the coordinator channel
    if settings.telegram_coordinator_chat_id and chat_id != settings.telegram_coordinator_chat_id:
        return

    result = await db.execute(
        select(Transaction).where(Transaction.photo_request_message_id == reply_message_id)
    )
    transaction = result.scalar_one_or_none()

    if not transaction:
        log.debug("Photo reply to message_id=%s — no matching transaction found", reply_message_id)
        return

    # Telegram sends photos as an array of sizes; pick the largest (last) one
    photos = message["photo"]
    best_photo = max(photos, key=lambda p: p.get("file_size", 0))
    file_id = best_photo["file_id"]
    caption = message.get("caption", "")

    # Look up the sender's user record
    sender_tg_id = str(message["from"]["id"])
    user_result = await db.execute(
        select(User).where(User.telegram_chat_id == sender_tg_id)
    )
    sender = user_result.scalar_one_or_none()

    photo = TransactionPhoto(
        transaction_id=transaction.id,
        uploaded_by_user_id=sender.id if sender else None,
        telegram_file_id=file_id,
        telegram_message_id=str(message["message_id"]),
        telegram_chat_id=chat_id,
        caption=caption or None,
    )
    db.add(photo)

    # Clear the photo request flag now that we have a photo
    transaction.photo_requested_via_telegram = False
    transaction.photo_request_message_id = None

    await db.commit()

    await _send(
        chat_id,
        f"📷 Photo recorded for return #{transaction.id}. Thanks!",
    )
    log.info("Photo recorded for transaction %d from file_id %s", transaction.id, file_id)


async def _send(chat_id: str, text: str) -> None:
    bot = get_bot()
    if not bot:
        return
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    except Exception as e:
        log.warning("Bot send failed: %s", e)


async def cmd_start(chat_id: str) -> None:
    text = (
        "👋 <b>Cabinet Inventory Bot</b>\n\n"
        "Commands:\n"
        "/link <token> — Link your account\n"
        "/myitems — Your checked-out items\n"
        "/overdue — Overdue checkouts (coordinators)\n"
        "/status <item name> — Check item availability\n"
        "/requests — Pending requests (coordinators)\n"
        "/approve <id> — Approve a request\n"
        "/deny <id> [reason] — Deny a request\n\n"
        "Get your link token from the web app under Settings → Link Telegram."
    )
    await _send(chat_id, text)


async def cmd_link(chat_id: str, token: str, db: AsyncSession) -> None:
    result = await db.execute(
        select(User).where(User.telegram_link_token == token, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        await _send(chat_id, "❌ Invalid or expired link token. Generate a new one from the web app.")
        return

    user.telegram_chat_id = chat_id
    user.telegram_link_token = None  # consume the token
    await db.commit()

    await notify_account_linked(chat_id, user.full_name)


async def cmd_my_items(chat_id: str, db: AsyncSession) -> None:
    result = await db.execute(
        select(User).where(User.telegram_chat_id == chat_id, User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if not user:
        await _send(chat_id, "❌ Account not linked. Use /link <token> first.")
        return

    tx_result = await db.execute(
        select(Transaction)
        .where(
            Transaction.user_id == user.id,
            Transaction.status.in_([TransactionStatus.CHECKED_OUT, TransactionStatus.OVERDUE]),
        )
        .options(selectinload(Transaction.item))
        .order_by(Transaction.checked_out_at)
    )
    transactions = tx_result.scalars().all()

    if not transactions:
        await _send(chat_id, "✅ You have no items currently checked out.")
        return

    lines = ["<b>Your checked-out items:</b>"]
    for t in transactions:
        due = t.due_at.strftime("%b %d") if t.due_at else "no due date"
        status_icon = "⏰" if t.status == TransactionStatus.OVERDUE else "📦"
        lines.append(f"{status_icon} {t.item.name} × {t.quantity} — due {due} (#{t.id})")

    await _send(chat_id, "\n".join(lines))


async def cmd_overdue(chat_id: str, db: AsyncSession) -> None:
    # Only allow coordinators/admins
    user_result = await db.execute(
        select(User)
        .where(User.telegram_chat_id == chat_id, User.is_active == True)
        .options(selectinload(User.role))
    )
    user = user_result.scalar_one_or_none()
    if not user:
        await _send(chat_id, "❌ Account not linked. Use /link <token> first.")
        return

    if not (user.role.can_view_all_transactions or user.role.can_manage_users):
        await _send(chat_id, "❌ This command requires coordinator access.")
        return

    tx_result = await db.execute(
        select(Transaction)
        .where(Transaction.status == TransactionStatus.OVERDUE)
        .options(selectinload(Transaction.item), selectinload(Transaction.user))
        .order_by(Transaction.due_at)
    )
    transactions = tx_result.scalars().all()

    if not transactions:
        await _send(chat_id, "✅ No overdue checkouts.")
        return

    lines = [f"<b>⏰ Overdue items ({len(transactions)}):</b>"]
    for t in transactions:
        due = t.due_at.strftime("%b %d") if t.due_at else "?"
        handle = f"@{t.user.telegram_handle}" if t.user.telegram_handle else t.user.username
        lines.append(f"• {t.item.name} × {t.quantity} — {handle} — due {due} (#{t.id})")

    await _send(chat_id, "\n".join(lines))


async def cmd_item_status(chat_id: str, item_query: str, db: AsyncSession) -> None:
    from app.models.item import Item

    result = await db.execute(
        select(Item).where(Item.name.ilike(f"%{item_query}%"), Item.is_active == True).limit(5)
    )
    items = result.scalars().all()

    if not items:
        await _send(chat_id, f"❌ No active items matching '{item_query}'")
        return

    lines = [f"<b>Search results for '{item_query}':</b>"]
    for item in items:
        avail = "✅ Available" if item.quantity_available > 0 else "❌ Out of stock"
        lines.append(f"• {item.name} — {item.quantity_available}/{item.quantity_total} {avail}")

    await _send(chat_id, "\n".join(lines))


async def cmd_requests(chat_id: str, db: AsyncSession) -> None:
    from app.models.inventory_request import InventoryRequest, RequestStatus

    user_result = await db.execute(
        select(User)
        .where(User.telegram_chat_id == chat_id, User.is_active == True)
        .options(selectinload(User.role))
    )
    user = user_result.scalar_one_or_none()
    if not user:
        await _send(chat_id, "❌ Account not linked. Use /link <token> first.")
        return

    if not (user.role.can_approve_requests or user.role.can_manage_users):
        await _send(chat_id, "❌ This command requires coordinator access.")
        return

    result = await db.execute(
        select(InventoryRequest)
        .where(InventoryRequest.status == RequestStatus.PENDING)
        .options(
            selectinload(InventoryRequest.requester),
            selectinload(InventoryRequest.item),
            selectinload(InventoryRequest.bin),
        )
        .order_by(InventoryRequest.created_at)
        .limit(20)
    )
    requests = result.scalars().all()

    if not requests:
        await _send(chat_id, "✅ No pending requests.")
        return

    lines = [f"<b>📋 Pending requests ({len(requests)}):</b>"]
    for req in requests:
        requester = req.requester.username
        target = req.item.name if req.item else f"Bin #{req.bin_id}"
        qty = f" × {req.quantity_requested}" if req.quantity_requested > 1 else ""
        reason = f" — {req.reason}" if req.reason else ""
        lines.append(f"• #{req.id} {target}{qty} by {requester}{reason}")
        lines.append(f"  /approve {req.id}  |  /deny {req.id}")

    await _send(chat_id, "\n".join(lines))


async def cmd_approve(chat_id: str, request_id_str: str, db: AsyncSession) -> None:
    from app.models.inventory_request import InventoryRequest, RequestStatus
    from app.services.request_service import approve_request

    user_result = await db.execute(
        select(User)
        .where(User.telegram_chat_id == chat_id, User.is_active == True)
        .options(selectinload(User.role))
    )
    user = user_result.scalar_one_or_none()
    if not user:
        await _send(chat_id, "❌ Account not linked.")
        return

    if not (user.role.can_approve_requests or user.role.can_manage_users):
        await _send(chat_id, "❌ Permission denied.")
        return

    try:
        request_id = int(request_id_str)
    except ValueError:
        await _send(chat_id, "❌ Invalid request ID.")
        return

    try:
        req = await approve_request(db, request_id=request_id, approver_id=user.id, due_at=None)
        await db.commit()

        target_name = f"Bin #{req.bin_id}" if req.bin_id else f"Item #{req.item_id}"
        await _send(chat_id, f"✅ Request #{req.id} approved ({target_name}).")

        # Notify requester if linked
        requester_result = await db.execute(select(User).where(User.id == req.requester_id))
        requester = requester_result.scalar_one_or_none()
        if requester and requester.telegram_chat_id:
            from app.services.telegram_service import _send as tg_send
            await tg_send(
                requester.telegram_chat_id,
                f"✅ Your request #{req.id} for <b>{target_name}</b> has been approved!",
            )
    except Exception as e:
        await _send(chat_id, f"❌ Error: {e}")


async def cmd_deny(chat_id: str, request_id_str: str, reason: str | None, db: AsyncSession) -> None:
    from app.services.request_service import deny_request

    user_result = await db.execute(
        select(User)
        .where(User.telegram_chat_id == chat_id, User.is_active == True)
        .options(selectinload(User.role))
    )
    user = user_result.scalar_one_or_none()
    if not user:
        await _send(chat_id, "❌ Account not linked.")
        return

    if not (user.role.can_approve_requests or user.role.can_manage_users):
        await _send(chat_id, "❌ Permission denied.")
        return

    try:
        request_id = int(request_id_str)
    except ValueError:
        await _send(chat_id, "❌ Invalid request ID.")
        return

    try:
        req = await deny_request(
            db, request_id=request_id, approver_id=user.id, denial_reason=reason
        )
        await db.commit()
        await _send(chat_id, f"❌ Request #{req.id} denied.")

        requester_result = await db.execute(select(User).where(User.id == req.requester_id))
        requester = requester_result.scalar_one_or_none()
        if requester and requester.telegram_chat_id:
            from app.services.telegram_service import _send as tg_send
            reason_text = f"\nReason: {reason}" if reason else ""
            await tg_send(
                requester.telegram_chat_id,
                f"❌ Your request #{req.id} was denied.{reason_text}",
            )
    except Exception as e:
        await _send(chat_id, f"❌ Error: {e}")
