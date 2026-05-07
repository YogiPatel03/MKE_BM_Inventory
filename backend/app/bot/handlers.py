"""
Telegram bot command handlers.

Routing: the webhook endpoint calls handle_update(), which builds a BotContext
and dispatches to the appropriate command handler.

Identity contract:
  BotContext.reply_chat_id   — where the bot replies (group/topic ID or DM ID)
  BotContext.actor_telegram_id — who sent the command; used for DB user lookup

  In a private DM these are equal. In a group/topic, chat.id is the group ID
  while from.id is the individual user's Telegram ID. All user lookups use
  actor_telegram_id, never reply_chat_id, so group commands resolve the correct
  user.

  BotContext.message_thread_id is set for messages sent inside forum topics.
  Passing it to _send keeps bot replies inside the same topic.

  User.telegram_chat_id stores the user's personal DM chat ID (== from.id when
  linked from a private chat). /link sets telegram_chat_id = actor_telegram_id
  (from.id), never chat.id, so personal DMs always reach the individual user.
"""

import html as _html
import logging
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.receipt_record import ReceiptRecord
from app.models.transaction import Transaction, TransactionStatus
from app.models.transaction_photo import TransactionPhoto
from app.models.user import User
from app.services.telegram_service import get_bot, notify_account_linked

log = logging.getLogger(__name__)

_NOT_LINKED_MSG = (
    "❌ Account not linked. DM this bot, send /start, then /link &lt;token&gt;.\n"
    "Get your token from the web app: Settings → Link Telegram."
)


@dataclass
class BotContext:
    reply_chat_id: str
    actor_telegram_id: str
    actor_username: Optional[str]
    chat_type: str
    message_thread_id: Optional[int]
    text: str
    command: str
    args: list[str]


async def handle_update(body: dict[str, Any], db: AsyncSession) -> None:
    message = body.get("message") or body.get("edited_message")
    if not message:
        return

    sender = message.get("from")
    if not sender:
        # Channel posts have no "from"; nothing to act on.
        return

    chat = message.get("chat")
    if not chat or not chat.get("id"):
        log.debug("handle_update: skipping update with missing chat or chat.id")
        return

    sender_id = sender.get("id")
    if not sender_id:
        log.debug("handle_update: skipping update with missing from.id")
        return

    ctx = BotContext(
        reply_chat_id=str(chat["id"]),
        actor_telegram_id=str(sender_id),
        actor_username=sender.get("username"),
        chat_type=chat.get("type", "private"),
        message_thread_id=message.get("message_thread_id"),
        text=message.get("text", ""),
        command="",
        args=[],
    )

    # Photo reply: could be a return condition photo or a receipt photo
    if message.get("photo") and message.get("reply_to_message"):
        handled = await handle_receipt_photo_reply(message, ctx.reply_chat_id, ctx.message_thread_id, db)
        if not handled:
            await handle_photo_reply(message, ctx.reply_chat_id, ctx.message_thread_id, db)
        return

    if not ctx.text.startswith("/"):
        return

    parts = ctx.text.split()
    ctx.command = parts[0].lower().split("@")[0]  # strip @BotName suffix
    ctx.args = parts[1:]

    if ctx.command == "/start":
        await cmd_start(ctx)
    elif ctx.command == "/help" or ctx.command == "/commands":
        await cmd_help(ctx)
    elif ctx.command == "/whereami":
        await cmd_whereami(ctx)
    elif ctx.command == "/whoami":
        await cmd_whoami(ctx, db)
    elif ctx.command == "/link" and len(ctx.args) == 1:
        await cmd_link(ctx, ctx.args[0], db)
    elif ctx.command == "/myitems":
        await cmd_my_items(ctx, db)
    elif ctx.command == "/overdue":
        await cmd_overdue(ctx, db)
    elif ctx.command == "/status" and ctx.args:
        item_query = " ".join(ctx.args)
        await cmd_item_status(ctx, item_query, db)
    elif ctx.command == "/requests":
        await cmd_requests(ctx, db)
    elif ctx.command == "/approve" and len(ctx.args) == 1:
        await cmd_approve(ctx, ctx.args[0], db)
    elif ctx.command == "/deny" and ctx.args:
        reason = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else None
        await cmd_deny(ctx, ctx.args[0], reason, db)
    else:
        await _send(
            ctx.reply_chat_id,
            "Unknown command. Try /help for a list of commands.",
            message_thread_id=ctx.message_thread_id,
        )


async def handle_photo_reply(
    message: dict[str, Any],
    chat_id: str,
    message_thread_id: Optional[int],
    db: AsyncSession,
) -> None:
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

    # Look up the sender's user record by from.id (identity, not chat.id)
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
        message_thread_id=message_thread_id,
    )
    log.info("Photo recorded for transaction %d from file_id %s", transaction.id, file_id)


async def handle_receipt_photo_reply(
    message: dict[str, Any],
    chat_id: str,
    message_thread_id: Optional[int],
    db: AsyncSession,
) -> bool:
    """
    Records a receipt photo when someone replies to the bot's purchase receipt-request message.
    Matches reply_to_message.message_id against ReceiptRecord.telegram_request_message_id.
    Returns True if a matching receipt record was found and updated, False otherwise.
    """
    reply_to = message["reply_to_message"]
    reply_message_id = str(reply_to.get("message_id", ""))

    if not reply_message_id:
        return False

    # Only process replies in the coordinator channel
    if settings.telegram_coordinator_chat_id and chat_id != settings.telegram_coordinator_chat_id:
        return False

    result = await db.execute(
        select(ReceiptRecord).where(
            ReceiptRecord.telegram_request_message_id == reply_message_id,
            ReceiptRecord.telegram_file_id.is_(None),  # not yet fulfilled
        )
    )
    receipt = result.scalar_one_or_none()

    if not receipt:
        return False

    # Pick the largest photo size
    photos = message["photo"]
    best_photo = max(photos, key=lambda p: p.get("file_size", 0))
    file_id = best_photo["file_id"]

    receipt.telegram_file_id = file_id
    receipt.uploaded_via = "telegram"
    receipt.notes = message.get("caption") or receipt.notes

    # Look up sender for attribution by from.id (identity, not chat.id)
    sender_tg_id = str(message["from"]["id"])
    user_result = await db.execute(
        select(User).where(User.telegram_chat_id == sender_tg_id)
    )
    sender = user_result.scalar_one_or_none()
    if sender and not receipt.uploaded_by_user_id:
        receipt.uploaded_by_user_id = sender.id

    await db.commit()

    await _send(chat_id, f"📄 Receipt recorded (#{receipt.id}). Thanks!", message_thread_id=message_thread_id)
    log.info("Receipt photo recorded for receipt_record %d from file_id %s", receipt.id, file_id)
    return True


async def _send(chat_id: str, text: str, *, message_thread_id: Optional[int] = None) -> None:
    bot = get_bot()
    if not bot:
        return
    try:
        kwargs: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if message_thread_id is not None:
            kwargs["message_thread_id"] = message_thread_id
        await bot.send_message(**kwargs)
    except Exception as e:
        log.warning("Bot send failed: %s", e)


async def cmd_start(ctx: BotContext) -> None:
    text = (
        "👋 <b>Cabinet Inventory Bot</b>\n\n"
        "Commands:\n"
        "/link &lt;token&gt; — Link your account (DM only)\n"
        "/myitems — Your checked-out items\n"
        "/overdue — Overdue checkouts (coordinators)\n"
        "/status &lt;item name&gt; — Check item availability\n"
        "/requests — Pending requests (coordinators)\n"
        "/approve &lt;id&gt; — Approve a request\n"
        "/deny &lt;id&gt; [reason] — Deny a request\n"
        "/whoami — Show your linked account info\n"
        "/whereami — Show this chat's IDs (for setup)\n"
        "/help — Show this command list\n\n"
        "Get your link token from the web app under Settings → Link Telegram."
    )
    await _send(ctx.reply_chat_id, text, message_thread_id=ctx.message_thread_id)


async def cmd_help(ctx: BotContext) -> None:
    text = (
        "<b>Cabinet Inventory Bot — Commands</b>\n\n"
        "<b>Everyone:</b>\n"
        "  /link &lt;token&gt; — Link Telegram to your account (DM only)\n"
        "  /myitems — Your currently checked-out items\n"
        "  /status &lt;item&gt; — Check item availability\n"
        "  /whoami — Show your linked account info\n"
        "  /whereami — Show this chat's IDs (admin setup)\n\n"
        "<b>Coordinators / Group leads:</b>\n"
        "  /overdue — List all overdue checkouts\n"
        "  /requests — List pending inventory requests\n"
        "  /approve &lt;id&gt; — Approve a request\n"
        "  /deny &lt;id&gt; [reason] — Deny a request\n\n"
        "Get your link token from the web app: Settings → Link Telegram."
    )
    await _send(ctx.reply_chat_id, text, message_thread_id=ctx.message_thread_id)


async def cmd_whereami(ctx: BotContext) -> None:
    """
    Print chat_id, message_thread_id, actor_telegram_id, username, and chat_type.
    Used by admins to collect IDs for Render environment variables.
    """
    thread_line = (
        f"message_thread_id: <code>{ctx.message_thread_id}</code>"
        if ctx.message_thread_id is not None
        else "message_thread_id: (not a topic)"
    )
    username_line = (
        f"username: @{_html.escape(ctx.actor_username)}"
        if ctx.actor_username
        else "username: (none set)"
    )

    # Reverse-lookup: show group name if this thread is already mapped
    from app.services.telegram_service import get_group_for_thread_id
    group_hint = ""
    if ctx.message_thread_id is not None:
        group_name = get_group_for_thread_id(ctx.message_thread_id)
        if group_name:
            group_hint = f"\nmapped group: {_html.escape(group_name)}"

    text = (
        f"<b>📍 Where am I?</b>\n\n"
        f"chat_id: <code>{ctx.reply_chat_id}</code>\n"
        f"{thread_line}\n"
        f"actor_telegram_id: <code>{ctx.actor_telegram_id}</code>\n"
        f"{username_line}\n"
        f"chat_type: {_html.escape(ctx.chat_type)}"
        f"{group_hint}"
    )
    await _send(ctx.reply_chat_id, text, message_thread_id=ctx.message_thread_id)


async def cmd_whoami(ctx: BotContext, db: AsyncSession) -> None:
    """Print the linked app user's info, or explain how to link."""
    result = await db.execute(
        select(User)
        .where(User.telegram_chat_id == ctx.actor_telegram_id, User.is_active == True)
        .options(selectinload(User.role))
    )
    user = result.scalar_one_or_none()

    if not user:
        text = (
            "❌ <b>Not linked</b>\n\n"
            "Your Telegram account is not linked to any Cabinet Inventory user.\n\n"
            "To link:\n"
            "1. Go to the web app → Settings → Link Telegram\n"
            "2. Generate a link token\n"
            "3. Open a DM with this bot and send: /link &lt;token&gt;"
        )
    else:
        handle_line = f"\nTelegram: @{_html.escape(user.telegram_handle)}" if user.telegram_handle else ""
        role_line = f"\nRole: {_html.escape(user.role.name)}" if user.role else ""
        group_line = f"\nGroup: {_html.escape(user.group_name)}" if user.group_name else ""
        text = (
            f"👤 <b>Linked account</b>\n\n"
            f"Name: {_html.escape(user.full_name)}\n"
            f"Username: {_html.escape(user.username)}"
            f"{handle_line}"
            f"{role_line}"
            f"{group_line}"
        )
    await _send(ctx.reply_chat_id, text, message_thread_id=ctx.message_thread_id)


async def cmd_link(ctx: BotContext, token: str, db: AsyncSession) -> None:
    if ctx.chat_type != "private":
        await _send(
            ctx.reply_chat_id,
            "⚠️ For security, please DM me and send /link &lt;token&gt; using the token from Settings.",
            message_thread_id=ctx.message_thread_id,
        )
        return

    result = await db.execute(
        select(User).where(User.telegram_link_token == token, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        await _send(ctx.reply_chat_id, "❌ Invalid or expired link token. Generate a new one from the web app.")
        return

    # Prevent two app users from sharing the same Telegram identity.
    dup_result = await db.execute(
        select(User).where(User.telegram_chat_id == ctx.actor_telegram_id, User.is_active == True)
    )
    existing = dup_result.scalar_one_or_none()
    if existing and existing.id != user.id:
        await _send(
            ctx.reply_chat_id,
            "❌ This Telegram account is already linked to another user. Contact an admin.",
        )
        return

    user.telegram_chat_id = ctx.actor_telegram_id  # personal DM chat ID; equals reply_chat_id in private
    user.telegram_link_token = None  # consume the one-time token
    if ctx.actor_username:
        user.telegram_handle = ctx.actor_username

    try:
        await db.commit()
    except IntegrityError:
        # Race: two concurrent /link requests from the same Telegram actor both passed
        # the pre-check above. The losing commit hits the unique constraint; roll back
        # so the token is preserved and the user can try again.
        await db.rollback()
        await _send(
            ctx.reply_chat_id,
            "❌ This Telegram account is already linked to another user. Contact an admin.",
        )
        return

    await notify_account_linked(ctx.reply_chat_id, user.full_name)


async def cmd_my_items(ctx: BotContext, db: AsyncSession) -> None:
    result = await db.execute(
        select(User).where(User.telegram_chat_id == ctx.actor_telegram_id, User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if not user:
        await _send(ctx.reply_chat_id, _NOT_LINKED_MSG, message_thread_id=ctx.message_thread_id)
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
        await _send(ctx.reply_chat_id, "✅ You have no items currently checked out.", message_thread_id=ctx.message_thread_id)
        return

    lines = ["<b>Your checked-out items:</b>"]
    for t in transactions:
        due = t.due_at.strftime("%b %d") if t.due_at else "no due date"
        status_icon = "⏰" if t.status == TransactionStatus.OVERDUE else "📦"
        lines.append(f"{status_icon} {t.item.name} × {t.quantity} — due {due} (#{t.id})")

    await _send(ctx.reply_chat_id, "\n".join(lines), message_thread_id=ctx.message_thread_id)


async def cmd_overdue(ctx: BotContext, db: AsyncSession) -> None:
    user_result = await db.execute(
        select(User)
        .where(User.telegram_chat_id == ctx.actor_telegram_id, User.is_active == True)
        .options(selectinload(User.role))
    )
    user = user_result.scalar_one_or_none()
    if not user:
        await _send(ctx.reply_chat_id, _NOT_LINKED_MSG, message_thread_id=ctx.message_thread_id)
        return

    if not (user.role.can_view_all_transactions or user.role.can_manage_users):
        await _send(ctx.reply_chat_id, "❌ This command requires coordinator access.", message_thread_id=ctx.message_thread_id)
        return

    tx_result = await db.execute(
        select(Transaction)
        .where(Transaction.status == TransactionStatus.OVERDUE)
        .options(selectinload(Transaction.item), selectinload(Transaction.user))
        .order_by(Transaction.due_at)
    )
    transactions = tx_result.scalars().all()

    if not transactions:
        await _send(ctx.reply_chat_id, "✅ No overdue checkouts.", message_thread_id=ctx.message_thread_id)
        return

    lines = [f"<b>⏰ Overdue items ({len(transactions)}):</b>"]
    for t in transactions:
        due = t.due_at.strftime("%b %d") if t.due_at else "?"
        handle = f"@{t.user.telegram_handle}" if t.user.telegram_handle else t.user.username
        lines.append(f"• {t.item.name} × {t.quantity} — {handle} — due {due} (#{t.id})")

    await _send(ctx.reply_chat_id, "\n".join(lines), message_thread_id=ctx.message_thread_id)


async def cmd_item_status(ctx: BotContext, item_query: str, db: AsyncSession) -> None:
    from app.models.item import Item

    result = await db.execute(
        select(Item).where(Item.name.ilike(f"%{item_query}%"), Item.is_active == True).limit(5)
    )
    items = result.scalars().all()

    if not items:
        await _send(ctx.reply_chat_id, f"❌ No active items matching '{item_query}'", message_thread_id=ctx.message_thread_id)
        return

    lines = [f"<b>Search results for '{item_query}':</b>"]
    for item in items:
        avail = "✅ Available" if item.quantity_available > 0 else "❌ Out of stock"
        lines.append(f"• {item.name} — {item.quantity_available}/{item.quantity_total} {avail}")

    await _send(ctx.reply_chat_id, "\n".join(lines), message_thread_id=ctx.message_thread_id)


async def cmd_requests(ctx: BotContext, db: AsyncSession) -> None:
    from app.models.inventory_request import InventoryRequest, RequestStatus
    from app.core.permissions import is_group_lead

    user_result = await db.execute(
        select(User)
        .where(User.telegram_chat_id == ctx.actor_telegram_id, User.is_active == True)
        .options(selectinload(User.role))
    )
    user = user_result.scalar_one_or_none()
    if not user:
        await _send(ctx.reply_chat_id, _NOT_LINKED_MSG, message_thread_id=ctx.message_thread_id)
        return

    if not (user.role.can_approve_requests or user.role.can_manage_users):
        await _send(ctx.reply_chat_id, "❌ This command requires coordinator access.", message_thread_id=ctx.message_thread_id)
        return

    query = (
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

    # Group leads see only their own group's requests — mirrors web list_requests.
    if is_group_lead(user):
        query = query.join(User, InventoryRequest.requester_id == User.id).where(
            User.group_name == user.group_name
        )

    result = await db.execute(query)
    requests = result.scalars().all()

    if not requests:
        await _send(ctx.reply_chat_id, "✅ No pending requests.", message_thread_id=ctx.message_thread_id)
        return

    lines = [f"<b>📋 Pending requests ({len(requests)}):</b>"]
    for req in requests:
        requester = req.requester.username
        target = req.item.name if req.item else f"Bin #{req.bin_id}"
        qty = f" × {req.quantity_requested}" if req.quantity_requested > 1 else ""
        reason = f" — {req.reason}" if req.reason else ""
        lines.append(f"• #{req.id} {target}{qty} by {requester}{reason}")
        lines.append(f"  /approve {req.id}  |  /deny {req.id}")

    await _send(ctx.reply_chat_id, "\n".join(lines), message_thread_id=ctx.message_thread_id)


async def cmd_approve(ctx: BotContext, request_id_str: str, db: AsyncSession) -> None:
    from app.models.inventory_request import InventoryRequest, RequestStatus
    from app.services.request_service import approve_request
    from app.core.permissions import check_request_scope

    user_result = await db.execute(
        select(User)
        .where(User.telegram_chat_id == ctx.actor_telegram_id, User.is_active == True)
        .options(selectinload(User.role))
    )
    user = user_result.scalar_one_or_none()
    if not user:
        await _send(ctx.reply_chat_id, _NOT_LINKED_MSG, message_thread_id=ctx.message_thread_id)
        return

    if not (user.role.can_approve_requests or user.role.can_manage_users):
        await _send(ctx.reply_chat_id, "❌ Permission denied.", message_thread_id=ctx.message_thread_id)
        return

    try:
        request_id = int(request_id_str)
    except ValueError:
        await _send(ctx.reply_chat_id, "❌ Invalid request ID.", message_thread_id=ctx.message_thread_id)
        return

    # Group scope check — same rule as the web approve endpoint.
    scope_row = (await db.execute(
        select(User.group_name)
        .select_from(InventoryRequest)
        .join(User, User.id == InventoryRequest.requester_id)
        .where(InventoryRequest.id == request_id)
    )).first()
    if scope_row is None:
        await _send(ctx.reply_chat_id, f"❌ Request #{request_id} not found.", message_thread_id=ctx.message_thread_id)
        return
    if not check_request_scope(user, scope_row[0]):
        await _send(ctx.reply_chat_id, "❌ Permission denied: this request belongs to a different group.", message_thread_id=ctx.message_thread_id)
        return

    # Mutation — isolated from post-commit notifications.
    from app.core.exceptions import InsufficientStockError, TransactionConflictError
    try:
        req = await approve_request(db, request_id=request_id, approver_id=user.id, due_at=None)
        await db.commit()
    except TransactionConflictError as e:
        await db.rollback()
        detail = str(e.detail)
        if any(s in detail for s in ("FULFILLED", "DENIED", "CANCELLED")):
            await _send(ctx.reply_chat_id, f"❌ Request #{request_id} has already been processed.", message_thread_id=ctx.message_thread_id)
        else:
            await _send(ctx.reply_chat_id, f"❌ Cannot approve request #{request_id}: {_html.escape(detail)}", message_thread_id=ctx.message_thread_id)
        return
    except InsufficientStockError as e:
        await db.rollback()
        await _send(ctx.reply_chat_id, f"❌ Cannot approve: {_html.escape(str(e.detail))}", message_thread_id=ctx.message_thread_id)
        return
    except Exception:
        await db.rollback()
        log.exception("Unexpected error in cmd_approve for request %s", request_id)
        await _send(ctx.reply_chat_id, "❌ Could not process the request. Please try again or check the web app.", message_thread_id=ctx.message_thread_id)
        return

    # Commit succeeded — resolve real name, report, and notify (non-fatal).
    from app.models.item import Item
    from app.models.bin import Bin
    target_name = "unknown item"
    if req.item_id:
        item = (await db.execute(select(Item).where(Item.id == req.item_id))).scalar_one_or_none()
        if item:
            target_name = item.name
    elif req.bin_id:
        bin_obj = (await db.execute(select(Bin).where(Bin.id == req.bin_id))).scalar_one_or_none()
        if bin_obj:
            target_name = f"Bin: {bin_obj.label}"

    await _send(ctx.reply_chat_id, f"✅ Request #{req.id} approved ({_html.escape(target_name)}).", message_thread_id=ctx.message_thread_id)

    try:
        requester = (await db.execute(select(User).where(User.id == req.requester_id))).scalar_one_or_none()
        if requester and requester.telegram_chat_id:
            from app.services.telegram_service import notify_request_approved
            await notify_request_approved(requester.telegram_chat_id, target_name, req.id)
    except Exception:
        log.warning("Failed to notify requester for request %d", req.id)


async def cmd_deny(ctx: BotContext, request_id_str: str, reason: Optional[str], db: AsyncSession) -> None:
    from app.services.request_service import deny_request
    from app.models.inventory_request import InventoryRequest
    from app.core.permissions import check_request_scope

    user_result = await db.execute(
        select(User)
        .where(User.telegram_chat_id == ctx.actor_telegram_id, User.is_active == True)
        .options(selectinload(User.role))
    )
    user = user_result.scalar_one_or_none()
    if not user:
        await _send(ctx.reply_chat_id, _NOT_LINKED_MSG, message_thread_id=ctx.message_thread_id)
        return

    if not (user.role.can_approve_requests or user.role.can_manage_users):
        await _send(ctx.reply_chat_id, "❌ Permission denied.", message_thread_id=ctx.message_thread_id)
        return

    try:
        request_id = int(request_id_str)
    except ValueError:
        await _send(ctx.reply_chat_id, "❌ Invalid request ID.", message_thread_id=ctx.message_thread_id)
        return

    # Group scope check — same rule as the web deny endpoint.
    scope_row = (await db.execute(
        select(User.group_name)
        .select_from(InventoryRequest)
        .join(User, User.id == InventoryRequest.requester_id)
        .where(InventoryRequest.id == request_id)
    )).first()
    if scope_row is None:
        await _send(ctx.reply_chat_id, f"❌ Request #{request_id} not found.", message_thread_id=ctx.message_thread_id)
        return
    if not check_request_scope(user, scope_row[0]):
        await _send(ctx.reply_chat_id, "❌ Permission denied: this request belongs to a different group.", message_thread_id=ctx.message_thread_id)
        return

    # Mutation — isolated from post-commit notifications.
    from app.core.exceptions import TransactionConflictError
    try:
        req = await deny_request(
            db, request_id=request_id, approver_id=user.id, denial_reason=reason
        )
        await db.commit()
    except TransactionConflictError:
        await db.rollback()
        await _send(ctx.reply_chat_id, f"❌ Request #{request_id} has already been processed.", message_thread_id=ctx.message_thread_id)
        return
    except Exception:
        await db.rollback()
        log.exception("Unexpected error in cmd_deny for request %s", request_id)
        await _send(ctx.reply_chat_id, "❌ Could not process the request. Please try again or check the web app.", message_thread_id=ctx.message_thread_id)
        return

    # Commit succeeded — resolve real name, report, and notify (non-fatal).
    from app.models.item import Item
    from app.models.bin import Bin
    target_name = "unknown item"
    if req.item_id:
        item = (await db.execute(select(Item).where(Item.id == req.item_id))).scalar_one_or_none()
        if item:
            target_name = item.name
    elif req.bin_id:
        bin_obj = (await db.execute(select(Bin).where(Bin.id == req.bin_id))).scalar_one_or_none()
        if bin_obj:
            target_name = f"Bin: {bin_obj.label}"

    reason_line = f"\nReason: {_html.escape(reason)}" if reason else ""
    await _send(ctx.reply_chat_id, f"❌ Request #{req.id} denied ({_html.escape(target_name)}).{reason_line}", message_thread_id=ctx.message_thread_id)

    try:
        requester = (await db.execute(select(User).where(User.id == req.requester_id))).scalar_one_or_none()
        if requester and requester.telegram_chat_id:
            from app.services.telegram_service import notify_request_denied
            await notify_request_denied(requester.telegram_chat_id, target_name, req.id, reason)
    except Exception:
        log.warning("Failed to notify requester for request %d", req.id)
