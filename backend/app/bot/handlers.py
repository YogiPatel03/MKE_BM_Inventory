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
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.checklist import Checklist, ChecklistItem, GroupName
from app.models.receipt_record import ReceiptRecord
from app.models.transaction import Transaction, TransactionStatus
from app.models.transaction_photo import TransactionPhoto
from app.models.user import User
from app.services.telegram_service import get_bot, notify_account_linked, notify_checklist_item_status_changed

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
    # ── Checklist commands ──────────────────────────────────────────────────
    elif ctx.command == "/tasks":
        await cmd_tasks(ctx, db)
    elif ctx.command == "/mytasks":
        await cmd_mytasks(ctx, db)
    elif ctx.command == "/task" and ctx.args:
        await cmd_task(ctx, ctx.args[0], db)
    elif ctx.command == "/done" and ctx.args:
        note = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else None
        await cmd_done(ctx, ctx.args[0], note, db)
    elif ctx.command == "/undo" and ctx.args:
        reason = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else None
        await cmd_undo(ctx, ctx.args[0], reason, db)
    elif ctx.command == "/claim" and ctx.args:
        await cmd_claim(ctx, ctx.args[0], db)
    elif ctx.command == "/unclaim" and ctx.args:
        await cmd_unclaim(ctx, ctx.args[0], db)
    elif ctx.command == "/assign" and len(ctx.args) >= 2:
        await cmd_assign(ctx, ctx.args[0], ctx.args[1], db)
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


async def _send_chunks(chat_id: str, text: str, *, message_thread_id: Optional[int] = None) -> None:
    """Send a potentially long message split into Telegram-safe chunks."""
    from app.bot.checklist_helpers import split_messages
    for chunk in split_messages(text):
        await _send(chat_id, chunk, message_thread_id=message_thread_id)


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
        "<b>Checklist:</b>\n"
        "  /tasks — Current week's task list\n"
        "  /mytasks — Tasks assigned to you\n"
        "  /task &lt;id&gt; — Task details\n"
        "  /done &lt;id&gt; [note] — Mark task complete\n"
        "  /undo &lt;id&gt; [reason] — Mark task incomplete\n"
        "  /claim &lt;id&gt; — Claim a task\n"
        "  /unclaim &lt;id&gt; — Unclaim a task\n"
        "  /assign &lt;id&gt; me|everyone|@username — Assign task\n\n"
        "<b>Inventory:</b>\n"
        "  /link &lt;token&gt; — Link your account (DM only)\n"
        "  /myitems — Your checked-out items\n"
        "  /overdue — Overdue checkouts (coordinators)\n"
        "  /status &lt;item name&gt; — Check item availability\n"
        "  /requests — Pending requests (coordinators)\n"
        "  /approve &lt;id&gt; — Approve a request\n"
        "  /deny &lt;id&gt; [reason] — Deny a request\n"
        "  /whoami — Show your linked account info\n"
        "  /whereami — Show this chat's IDs (for setup)\n"
        "  /help — Show this command list\n\n"
        "Get your link token from the web app under Settings → Link Telegram."
    )
    await _send(ctx.reply_chat_id, text, message_thread_id=ctx.message_thread_id)


async def cmd_help(ctx: BotContext) -> None:
    text = (
        "<b>Cabinet Inventory Bot — Commands</b>\n\n"
        "<b>Checklist (all linked users):</b>\n"
        "  /tasks — Current week's task list for your group\n"
        "  /mytasks — Tasks assigned to you or everyone\n"
        "  /task &lt;id&gt; — Read-only task details\n"
        "  /done &lt;id&gt; [note] — Mark a task complete\n"
        "  /undo &lt;id&gt; [reason] — Mark a task incomplete again\n\n"
        "<b>Checklist (coordinators / group leads):</b>\n"
        "  /claim &lt;id&gt; — Assign task to yourself\n"
        "  /unclaim &lt;id&gt; — Remove your assignment\n"
        "  /assign &lt;id&gt; me — Same as /claim\n"
        "  /assign &lt;id&gt; everyone — Set task to shared responsibility\n"
        "  /assign &lt;id&gt; @username — Assign to a linked user\n\n"
        "<b>Inventory (all linked users):</b>\n"
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
    from app.services.checklist_service import (
        add_return_task_for_bin_transaction,
        add_return_task_for_transaction,
    )
    try:
        req, txn, bin_txn = await approve_request(
            db, request_id=request_id, approver_id=user.id, due_at=None
        )
        # Wire Sabha return task before commit.
        requester_for_task = (await db.execute(
            select(User).where(User.id == req.requester_id)
        )).scalar_one_or_none()
        if requester_for_task:
            if txn:
                await add_return_task_for_transaction(db, txn, requester_for_task)
            elif bin_txn:
                await add_return_task_for_bin_transaction(db, bin_txn, requester_for_task)
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


# ─── Checklist commands ───────────────────────────────────────────────────────


async def _resolve_actor(ctx: BotContext, db: AsyncSession):
    """Look up the linked User for this Telegram actor. Returns None if not linked."""
    result = await db.execute(
        select(User)
        .where(User.telegram_chat_id == ctx.actor_telegram_id, User.is_active == True)
        .options(selectinload(User.role))
    )
    return result.scalar_one_or_none()


async def _load_task_with_checklist(task_id: int, db: AsyncSession):
    """Load a ChecklistItem with its checklist and assignments for permission checks."""
    result = await db.execute(
        select(ChecklistItem)
        .where(ChecklistItem.id == task_id)
        .options(
            selectinload(ChecklistItem.assignee),
            selectinload(ChecklistItem.completed_by),
            selectinload(ChecklistItem.subchecklist),
            selectinload(ChecklistItem.checklist).selectinload(Checklist.assignments),
        )
    )
    return result.scalar_one_or_none()


async def cmd_tasks(ctx: BotContext, db: AsyncSession) -> None:
    """Show the current week's task list for the relevant group."""
    from app.bot.checklist_helpers import (
        can_view_checklist, format_full_checklist, load_checklist_for_group,
    )
    from app.services.telegram_service import get_group_for_thread_id

    user = await _resolve_actor(ctx, db)

    # Determine group: topic mapping > explicit arg (admins) > user's own group
    group_name: Optional[str] = None

    if ctx.message_thread_id is not None:
        group_name = get_group_for_thread_id(ctx.message_thread_id)

    if not group_name and ctx.args and user:
        can_manage = user.role.can_manage_users or user.role.can_manage_inventory
        if can_manage:
            arg = ctx.args[0].upper()
            if arg in GroupName.ALL:
                group_name = arg

    if not group_name:
        if not user:
            await _send(ctx.reply_chat_id, _NOT_LINKED_MSG, message_thread_id=ctx.message_thread_id)
            return
        if not user.group_name:
            await _send(ctx.reply_chat_id, "❌ Your account has no group assigned. Contact an admin.", message_thread_id=ctx.message_thread_id)
            return
        group_name = user.group_name

    if not user:
        await _send(ctx.reply_chat_id, _NOT_LINKED_MSG, message_thread_id=ctx.message_thread_id)
        return

    checklist = await load_checklist_for_group(db, group_name)
    if not checklist:
        await _send(ctx.reply_chat_id, "📋 No checklist found for this week yet.", message_thread_id=ctx.message_thread_id)
        return

    if not can_view_checklist(user, checklist):
        await _send(ctx.reply_chat_id, "❌ You don't have access to this group's checklist.", message_thread_id=ctx.message_thread_id)
        return

    await _send_chunks(ctx.reply_chat_id, format_full_checklist(checklist), message_thread_id=ctx.message_thread_id)


async def cmd_mytasks(ctx: BotContext, db: AsyncSession) -> None:
    """Show tasks assigned to the actor or everyone tasks for their group."""
    from app.bot.checklist_helpers import format_task_line, load_checklist_for_group, split_messages

    user = await _resolve_actor(ctx, db)
    if not user:
        await _send(ctx.reply_chat_id, _NOT_LINKED_MSG, message_thread_id=ctx.message_thread_id)
        return

    if not user.group_name:
        await _send(ctx.reply_chat_id, "❌ Your account has no group assigned. Contact an admin.", message_thread_id=ctx.message_thread_id)
        return

    checklist = await load_checklist_for_group(db, user.group_name)
    if not checklist:
        await _send(ctx.reply_chat_id, "📋 No checklist found for this week.", message_thread_id=ctx.message_thread_id)
        return

    my_tasks = [
        t for t in sorted(checklist.items, key=lambda t: t.item_order)
        if t.assignee_id == user.id or t.assignee_id is None
    ]

    if not my_tasks:
        await _send(ctx.reply_chat_id, "✅ No tasks assigned to you this week.", message_thread_id=ctx.message_thread_id)
        return

    incomplete = [t for t in my_tasks if not t.is_completed]
    complete = [t for t in my_tasks if t.is_completed]

    group_display = GroupName.DISPLAY.get(user.group_name, user.group_name)
    lines = [f"<b>📋 My tasks — {_html.escape(group_display)}</b>"]

    if incomplete:
        lines.append("\n<b>To do:</b>")
        for task in incomplete:
            lines.append(f"  {format_task_line(task)}")

    if complete:
        lines.append("\n<b>Done:</b>")
        for task in complete:
            lines.append(f"  {format_task_line(task)}")

    await _send_chunks(ctx.reply_chat_id, "\n".join(lines), message_thread_id=ctx.message_thread_id)


async def cmd_task(ctx: BotContext, task_id_str: str, db: AsyncSession) -> None:
    """Show read-only task details. Never modifies DB state."""
    from app.bot.checklist_helpers import can_view_checklist

    user = await _resolve_actor(ctx, db)
    if not user:
        await _send(ctx.reply_chat_id, _NOT_LINKED_MSG, message_thread_id=ctx.message_thread_id)
        return

    try:
        task_id = int(task_id_str)
    except ValueError:
        await _send(ctx.reply_chat_id, "❌ Invalid task ID.", message_thread_id=ctx.message_thread_id)
        return

    task = await _load_task_with_checklist(task_id, db)
    if not task:
        await _send(ctx.reply_chat_id, f"❌ Task #{task_id} not found.", message_thread_id=ctx.message_thread_id)
        return

    if not can_view_checklist(user, task.checklist):
        await _send(ctx.reply_chat_id, "❌ You don't have access to this task.", message_thread_id=ctx.message_thread_id)
        return

    group_display = GroupName.DISPLAY.get(task.checklist.group_name, task.checklist.group_name)
    section = task.subchecklist.title if task.subchecklist else "Unsectioned"
    status_str = "✅ Done" if task.is_completed else "⬜ Incomplete"

    if task.assignee_id is not None:
        assignee_str = _html.escape(task.assignee.full_name) if task.assignee else "unknown"
    else:
        assignee_str = "everyone"

    lines = [
        f"<b>Task #{task.id}</b>",
        f"<b>{_html.escape(task.title)}</b>",
        f"Group: {_html.escape(group_display)}",
        f"Section: {_html.escape(section)}",
        f"Assigned: {assignee_str}",
        f"Status: {status_str}",
    ]

    if task.is_completed:
        if task.completed_by:
            lines.append(f"Completed by: {_html.escape(task.completed_by.full_name)}")
        if task.completion_notes:
            lines.append(f"Notes: {_html.escape(task.completion_notes)}")

    if task.description:
        lines.append(f"Description: {_html.escape(task.description)}")

    if task.is_auto_generated:
        lines.append("<i>Auto-generated return task</i>")

    lines.append("")
    lines.append("<b>Suggested commands:</b>")
    if not task.is_completed and not (task.is_auto_generated and task.auto_type in ("ITEM_RETURN", "BIN_RETURN")):
        lines.append(f"/done {task.id}  — mark complete")
        lines.append(f"/claim {task.id}  — claim this task")
        lines.append(f"/assign {task.id} me  — assign to yourself")
    elif task.is_completed:
        lines.append(f"/undo {task.id}  — mark incomplete")

    await _send(ctx.reply_chat_id, "\n".join(lines), message_thread_id=ctx.message_thread_id)


async def cmd_done(ctx: BotContext, task_id_str: str, note: Optional[str], db: AsyncSession) -> None:
    """Mark a checklist task complete. Mirrors website complete_item permission rules."""
    from app.bot.checklist_helpers import can_view_checklist, can_complete_on
    from app.services.checklist_service import complete_checklist_item

    user = await _resolve_actor(ctx, db)
    if not user:
        await _send(ctx.reply_chat_id, _NOT_LINKED_MSG, message_thread_id=ctx.message_thread_id)
        return

    try:
        task_id = int(task_id_str)
    except ValueError:
        await _send(ctx.reply_chat_id, "❌ Invalid task ID.", message_thread_id=ctx.message_thread_id)
        return

    task = await _load_task_with_checklist(task_id, db)
    if not task:
        await _send(ctx.reply_chat_id, f"❌ Task #{task_id} not found.", message_thread_id=ctx.message_thread_id)
        return

    if not can_view_checklist(user, task.checklist):
        await _send(ctx.reply_chat_id, "❌ You don't have access to this task.", message_thread_id=ctx.message_thread_id)
        return

    # Block auto-generated ITEM_RETURN/BIN_RETURN — same as website 409 rule
    if task.is_auto_generated and task.auto_type in ("ITEM_RETURN", "BIN_RETURN") and not task.is_completed:
        await _send(
            ctx.reply_chat_id,
            "❌ This is an auto-generated return task. "
            "Return the item through the checkout return flow — it will complete automatically.",
            message_thread_id=ctx.message_thread_id,
        )
        return

    if not can_complete_on(user, task.checklist):
        if any(a.user_id == user.id for a in task.checklist.assignments):
            denial_msg = "❌ You can only mark tasks done on checklists for your own group."
        else:
            denial_msg = "❌ You must be assigned to this checklist to mark tasks done."
        await _send(ctx.reply_chat_id, denial_msg, message_thread_id=ctx.message_thread_id)
        return

    if task.is_completed:
        await _send(ctx.reply_chat_id, f"✅ Task #{task_id} is already complete.", message_thread_id=ctx.message_thread_id)
        return

    try:
        task, transitioned = await complete_checklist_item(db, item_id=task_id, user_id=user.id, notes=note)
        await db.commit()
    except Exception:
        await db.rollback()
        log.exception("cmd_done: error completing task %d", task_id)
        await _send(ctx.reply_chat_id, "❌ Could not mark task complete. Please try again.", message_thread_id=ctx.message_thread_id)
        return

    note_str = f" — {_html.escape(note)}" if note else ""
    await _send(ctx.reply_chat_id, f"✅ Task #{task_id} marked complete{note_str}.", message_thread_id=ctx.message_thread_id)
    if transitioned:
        try:
            await notify_checklist_item_status_changed(task, task.checklist, user, "completed")
        except Exception:
            log.exception("notify_checklist_item_status_changed failed for task_id=%s", task_id)


async def cmd_undo(ctx: BotContext, task_id_str: str, reason: Optional[str], db: AsyncSession) -> None:
    """Mark a checklist task incomplete again."""
    from app.bot.checklist_helpers import can_view_checklist, can_complete_on

    user = await _resolve_actor(ctx, db)
    if not user:
        await _send(ctx.reply_chat_id, _NOT_LINKED_MSG, message_thread_id=ctx.message_thread_id)
        return

    try:
        task_id = int(task_id_str)
    except ValueError:
        await _send(ctx.reply_chat_id, "❌ Invalid task ID.", message_thread_id=ctx.message_thread_id)
        return

    task = await _load_task_with_checklist(task_id, db)
    if not task:
        await _send(ctx.reply_chat_id, f"❌ Task #{task_id} not found.", message_thread_id=ctx.message_thread_id)
        return

    if not can_view_checklist(user, task.checklist):
        await _send(ctx.reply_chat_id, "❌ You don't have access to this task.", message_thread_id=ctx.message_thread_id)
        return

    # Auto-generated return tasks cannot be undone from Telegram regardless of role
    if task.is_auto_generated and task.auto_type in ("ITEM_RETURN", "BIN_RETURN"):
        await _send(
            ctx.reply_chat_id,
            "❌ Auto-generated return tasks cannot be undone from Telegram. "
            "Process the return flow on the website.",
            message_thread_id=ctx.message_thread_id,
        )
        return

    if not task.is_completed:
        await _send(ctx.reply_chat_id, f"⬜ Task #{task_id} is already incomplete.", message_thread_id=ctx.message_thread_id)
        return

    # Permission: same rule as /done and HTTP incomplete — currently assigned + same group for
    # non-managers. Managers (can_manage_inventory or can_manage_users) bypass this check.
    checklist = task.checklist
    if not can_complete_on(user, checklist):
        await _send(
            ctx.reply_chat_id,
            "❌ Permission denied. You must be assigned to this checklist to undo tasks.",
            message_thread_id=ctx.message_thread_id,
        )
        return

    try:
        task.is_completed = False
        task.completed_at = None
        task.completed_by_user_id = None
        if reason:
            task.completion_notes = (task.completion_notes or "") + f"\n[Undone via Telegram: {_html.escape(reason)}]"
        await db.commit()
    except Exception:
        await db.rollback()
        log.exception("cmd_undo: error undoing task %d", task_id)
        await _send(ctx.reply_chat_id, "❌ Could not undo task. Please try again.", message_thread_id=ctx.message_thread_id)
        return

    await _send(ctx.reply_chat_id, f"↩️ Task #{task_id} marked incomplete.", message_thread_id=ctx.message_thread_id)
    try:
        await notify_checklist_item_status_changed(task, task.checklist, user, "incomplete")
    except Exception:
        log.exception("notify_checklist_item_status_changed failed for task_id=%s", task_id)


async def cmd_claim(ctx: BotContext, task_id_str: str, db: AsyncSession) -> None:
    """Assign this task to the actor. Requires manage-tasks permission."""
    from app.bot.checklist_helpers import can_view_checklist, can_manage_tasks_on

    user = await _resolve_actor(ctx, db)
    if not user:
        await _send(ctx.reply_chat_id, _NOT_LINKED_MSG, message_thread_id=ctx.message_thread_id)
        return

    try:
        task_id = int(task_id_str)
    except ValueError:
        await _send(ctx.reply_chat_id, "❌ Invalid task ID.", message_thread_id=ctx.message_thread_id)
        return

    task = await _load_task_with_checklist(task_id, db)
    if not task:
        await _send(ctx.reply_chat_id, f"❌ Task #{task_id} not found.", message_thread_id=ctx.message_thread_id)
        return

    if not can_view_checklist(user, task.checklist):
        await _send(ctx.reply_chat_id, "❌ You don't have access to this task.", message_thread_id=ctx.message_thread_id)
        return

    if not can_manage_tasks_on(user, task.checklist):
        await _send(
            ctx.reply_chat_id,
            "❌ Only coordinators and assigned group leads can claim tasks.",
            message_thread_id=ctx.message_thread_id,
        )
        return

    if task.assignee_id == user.id:
        await _send(ctx.reply_chat_id, f"✅ Task #{task_id} is already assigned to you.", message_thread_id=ctx.message_thread_id)
        return

    try:
        task.assignee_id = user.id
        await db.commit()
    except Exception:
        await db.rollback()
        log.exception("cmd_claim: error claiming task %d", task_id)
        await _send(ctx.reply_chat_id, "❌ Could not claim task. Please try again.", message_thread_id=ctx.message_thread_id)
        return

    await _send(ctx.reply_chat_id, f"✅ Task #{task_id} claimed — assigned to you.", message_thread_id=ctx.message_thread_id)


async def cmd_unclaim(ctx: BotContext, task_id_str: str, db: AsyncSession) -> None:
    """Remove the current assignee from a task."""
    from app.bot.checklist_helpers import can_view_checklist, can_manage_tasks_on

    user = await _resolve_actor(ctx, db)
    if not user:
        await _send(ctx.reply_chat_id, _NOT_LINKED_MSG, message_thread_id=ctx.message_thread_id)
        return

    try:
        task_id = int(task_id_str)
    except ValueError:
        await _send(ctx.reply_chat_id, "❌ Invalid task ID.", message_thread_id=ctx.message_thread_id)
        return

    task = await _load_task_with_checklist(task_id, db)
    if not task:
        await _send(ctx.reply_chat_id, f"❌ Task #{task_id} not found.", message_thread_id=ctx.message_thread_id)
        return

    if not can_view_checklist(user, task.checklist):
        await _send(ctx.reply_chat_id, "❌ You don't have access to this task.", message_thread_id=ctx.message_thread_id)
        return

    if task.assignee_id is None:
        await _send(ctx.reply_chat_id, f"⬜ Task #{task_id} has no specific assignee.", message_thread_id=ctx.message_thread_id)
        return

    # Allow: admin/coordinator, group lead on this checklist, or the current assignee
    is_assignee = task.assignee_id == user.id
    if not can_manage_tasks_on(user, task.checklist) and not is_assignee:
        await _send(
            ctx.reply_chat_id,
            "❌ You can only unclaim tasks assigned to you.",
            message_thread_id=ctx.message_thread_id,
        )
        return

    try:
        task.assignee_id = None
        await db.commit()
    except Exception:
        await db.rollback()
        log.exception("cmd_unclaim: error unclaiming task %d", task_id)
        await _send(ctx.reply_chat_id, "❌ Could not unclaim task. Please try again.", message_thread_id=ctx.message_thread_id)
        return

    await _send(ctx.reply_chat_id, f"✅ Task #{task_id} unassigned — open for everyone.", message_thread_id=ctx.message_thread_id)


async def cmd_assign(ctx: BotContext, task_id_str: str, target: str, db: AsyncSession) -> None:
    """Assign a task: /assign <id> me|everyone|@username"""
    from app.bot.checklist_helpers import can_view_checklist, can_manage_tasks_on
    from app.services.telegram_service import send_user_dm

    user = await _resolve_actor(ctx, db)
    if not user:
        await _send(ctx.reply_chat_id, _NOT_LINKED_MSG, message_thread_id=ctx.message_thread_id)
        return

    try:
        task_id = int(task_id_str)
    except ValueError:
        await _send(ctx.reply_chat_id, "❌ Invalid task ID.", message_thread_id=ctx.message_thread_id)
        return

    task = await _load_task_with_checklist(task_id, db)
    if not task:
        await _send(ctx.reply_chat_id, f"❌ Task #{task_id} not found.", message_thread_id=ctx.message_thread_id)
        return

    if not can_view_checklist(user, task.checklist):
        await _send(ctx.reply_chat_id, "❌ You don't have access to this task.", message_thread_id=ctx.message_thread_id)
        return

    if not can_manage_tasks_on(user, task.checklist):
        await _send(
            ctx.reply_chat_id,
            "❌ Only coordinators and assigned group leads can assign tasks.",
            message_thread_id=ctx.message_thread_id,
        )
        return

    target_lower = target.lower()
    dm_user = None

    if target_lower == "me":
        task.assignee_id = user.id
        assignee_display = "you"

    elif target_lower == "everyone":
        task.assignee_id = None
        assignee_display = "everyone"

    elif target.startswith("@"):
        handle = target.lstrip("@")
        tgt_result = await db.execute(
            select(User).where(
                func.lower(User.telegram_handle) == handle.lower(),
                User.is_active == True,
            )
        )
        target_user = tgt_result.scalar_one_or_none()
        if not target_user:
            await _send(
                ctx.reply_chat_id,
                f"❌ I couldn't find a linked user for @{_html.escape(handle)}. "
                "Ask them to DM me /start and link their account first.",
                message_thread_id=ctx.message_thread_id,
            )
            return
        # Require Telegram linkage — the point of @username assignment is to DM them
        if not target_user.telegram_chat_id:
            await _send(
                ctx.reply_chat_id,
                f"❌ @{_html.escape(handle)} has not linked Telegram yet. "
                "Ask them to DM me /start and link their account first.",
                message_thread_id=ctx.message_thread_id,
            )
            return
        # Non-managers (group leads) may only assign users already on this checklist
        # (mirrors website PATCH /{checklist_id}/items/{item_id} eligibility rule)
        if not (user.role.can_manage_users or user.role.can_manage_inventory):
            if not any(a.user_id == target_user.id for a in task.checklist.assignments):
                await _send(
                    ctx.reply_chat_id,
                    "❌ You can only assign this task to users eligible for this checklist.",
                    message_thread_id=ctx.message_thread_id,
                )
                return
        task.assignee_id = target_user.id
        assignee_display = _html.escape(target_user.full_name)
        dm_user = target_user

    else:
        await _send(
            ctx.reply_chat_id,
            "❌ Invalid target. Use: /assign &lt;id&gt; me|everyone|@username",
            message_thread_id=ctx.message_thread_id,
        )
        return

    # Capture title before commit flushes the session
    task_title = task.title
    checklist_group = task.checklist.group_name

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        log.exception("cmd_assign: error assigning task %d", task_id)
        await _send(ctx.reply_chat_id, "❌ Could not assign task. Please try again.", message_thread_id=ctx.message_thread_id)
        return

    await _send(
        ctx.reply_chat_id,
        f"✅ Task #{task_id} assigned to {assignee_display}.",
        message_thread_id=ctx.message_thread_id,
    )

    # DM the assigned user (fire-and-forget — must not rollback the assignment)
    if dm_user:
        try:
            group_display = GroupName.DISPLAY.get(checklist_group, checklist_group)
            dm_text = (
                f"📋 <b>Task assigned to you</b>\n"
                f"Task #{task_id}: <b>{_html.escape(task_title)}</b>\n"
                f"Group: {_html.escape(group_display)}\n\n"
                f"View details: /task {task_id}"
            )
            await send_user_dm(dm_user, dm_text)
        except Exception:
            log.warning("cmd_assign: failed to DM assigned user %d for task %d", dm_user.id, task_id)
