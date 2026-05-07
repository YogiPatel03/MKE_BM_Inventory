"""
Tests for Telegram bot command handlers.

Validates that:
- reply_chat_id (chat.id) and actor_tg_id (from.id) are correctly separated
- Group commands resolve users by from.id, not the group's chat.id
- /link only works in private DMs and does not consume the token in groups
- Unlinked users receive actionable instructions
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import IntegrityError as SAIntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import handle_update
from app.core.security import hash_password
from app.models.bin import Bin
from app.models.bin_transaction import BinTransaction, BinTransactionStatus
from app.models.cabinet import Cabinet
from app.models.inventory_request import InventoryRequest, RequestStatus
from app.models.item import Item
from app.models.role import Role
from app.models.room import Room
from app.models.user import User


# ─── Update payload factories ─────────────────────────────────────────────────

def _private_update(user_id: int, username: str, text: str) -> dict:
    """Private DM update. chat.id == from.id in a private chat."""
    return {
        "update_id": 1,
        "message": {
            "message_id": 100,
            "from": {"id": user_id, "username": username, "first_name": "Test"},
            "chat": {"id": user_id, "type": "private"},
            "text": text,
        },
    }


def _group_update(user_id: int, username: str, group_id: int, text: str) -> dict:
    """Group chat update. chat.id is the group's negative ID; from.id is the user."""
    return {
        "update_id": 1,
        "message": {
            "message_id": 100,
            "from": {"id": user_id, "username": username, "first_name": "Test"},
            "chat": {"id": group_id, "type": "group"},
            "text": text,
        },
    }


# ─── Seed helpers ─────────────────────────────────────────────────────────────

def _user_role(**flags) -> Role:
    defaults = dict(
        can_manage_inventory=False,
        can_manage_cabinets=False,
        can_manage_bins=False,
        can_manage_users=False,
        can_process_any_transaction=False,
        can_view_all_transactions=False,
        can_view_audit_logs=False,
        can_approve_requests=False,
    )
    defaults.update(flags)
    return Role(name="USER", **defaults)


def _coord_role() -> Role:
    return Role(
        name="COORDINATOR",
        can_manage_inventory=True,
        can_manage_cabinets=True,
        can_manage_bins=True,
        can_manage_users=False,
        can_process_any_transaction=True,
        can_view_all_transactions=True,
        can_view_audit_logs=False,
        can_approve_requests=True,
    )


async def _seed_user(db: AsyncSession, *, telegram_chat_id: str | None = None, link_token: str | None = None, role: Role | None = None) -> User:
    if role is None:
        role = _user_role()
        db.add(role)
        await db.flush()
    user = User(
        full_name="Alice",
        username="alice",
        password_hash=hash_password("pass"),
        role_id=role.id,
        telegram_chat_id=telegram_chat_id,
        telegram_link_token=link_token,
    )
    db.add(user)
    await db.commit()
    return user


def _mock_bot():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


def _sent_text(mock_bot) -> str:
    """Return the text of the first send_message call."""
    return mock_bot.send_message.call_args.kwargs["text"]


def _sent_chat(mock_bot) -> str:
    """Return the chat_id of the first send_message call."""
    return str(mock_bot.send_message.call_args.kwargs["chat_id"])


# ─── Tests ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_private(db):
    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(111, "alice", "/start"), db)

    bot.send_message.assert_called_once()
    assert _sent_chat(bot) == "111"
    assert "Cabinet Inventory Bot" in _sent_text(bot)


@pytest.mark.asyncio
async def test_link_succeeds_private(db):
    user = await _seed_user(db, link_token="tok123")

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.bot.handlers.notify_account_linked", new=AsyncMock()):
        await handle_update(_private_update(999, "alice_tg", "/link tok123"), db)

    await db.refresh(user)
    assert user.telegram_chat_id == "999"
    assert user.telegram_handle == "alice_tg"
    assert user.telegram_link_token is None


@pytest.mark.asyncio
async def test_link_rejected_in_group(db):
    user = await _seed_user(db, link_token="tok456")

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_group_update(999, "alice_tg", -100123456, "/link tok456"), db)

    await db.refresh(user)
    # Token must NOT be consumed
    assert user.telegram_link_token == "tok456"
    assert user.telegram_chat_id is None

    bot.send_message.assert_called_once()
    # Reply goes to the group chat
    assert _sent_chat(bot) == "-100123456"
    # Message must guide user to DM
    text = _sent_text(bot)
    assert "private" in text.lower() or "DM" in text or "direct" in text.lower()


@pytest.mark.asyncio
async def test_myitems_group_resolves_by_from_id(db):
    """User linked with personal ID 999; sends /myitems from group — must resolve correctly."""
    await _seed_user(db, telegram_chat_id="999")

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_group_update(999, "alice_tg", -100999, "/myitems"), db)

    bot.send_message.assert_called_once()
    # Reply goes to the group
    assert _sent_chat(bot) == "-100999"
    # Must NOT say "not linked" — user was found
    assert "not linked" not in _sent_text(bot).lower()


@pytest.mark.asyncio
async def test_myitems_group_unlinked_gives_instructions(db):
    """No user linked with from.id 999 — must receive helpful instructions."""
    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_group_update(999, "ghost", -100999, "/myitems"), db)

    bot.send_message.assert_called_once()
    text = _sent_text(bot)
    assert "/link" in text or "DM" in text


@pytest.mark.asyncio
async def test_requests_group_resolves_actor(db):
    """Coordinator linked by personal ID; /requests from group must succeed."""
    role = _coord_role()
    db.add(role)
    await db.flush()
    await _seed_user(db, telegram_chat_id="777", role=role)

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_group_update(777, "coord_tg", -100888, "/requests"), db)

    bot.send_message.assert_called_once()
    # Reply goes to group
    assert _sent_chat(bot) == "-100888"
    # Must NOT be "not linked"
    assert "not linked" not in _sent_text(bot).lower()


@pytest.mark.asyncio
async def test_approve_group_resolves_actor(db):
    """Coordinator in a group can approve if from.id matches their telegram_chat_id."""
    # Setup roles and users
    coord_role = _coord_role()
    user_role = _user_role()
    db.add_all([coord_role, user_role])
    await db.flush()

    coord = User(
        full_name="Coord",
        username="coord",
        password_hash=hash_password("pass"),
        role_id=coord_role.id,
        telegram_chat_id="777",
    )
    requester = User(
        full_name="Alice",
        username="alice",
        password_hash=hash_password("pass"),
        role_id=user_role.id,
    )
    db.add_all([coord, requester])

    room = Room(name="Room A")
    db.add(room)
    await db.flush()
    cabinet = Cabinet(name="Cab A", room_id=room.id)
    db.add(cabinet)
    await db.flush()
    item = Item(name="Drill", quantity_total=5, quantity_available=5, cabinet_id=cabinet.id)
    db.add(item)
    await db.flush()

    req = InventoryRequest(
        requester_id=requester.id,
        item_id=item.id,
        quantity_requested=1,
        status=RequestStatus.PENDING,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.bot.handlers.notify_account_linked", new=AsyncMock()):
        await handle_update(
            _group_update(777, "coord_tg", -100888, f"/approve {req.id}"),
            db,
        )

    bot.send_message.assert_called()
    last_text = bot.send_message.call_args_list[-1].kwargs["text"]
    assert "approved" in last_text.lower() or "✅" in last_text
    assert "not linked" not in last_text.lower()


@pytest.mark.asyncio
async def test_deny_group_resolves_actor(db):
    """Coordinator in a group can deny if from.id matches their telegram_chat_id."""
    coord_role = _coord_role()
    user_role = _user_role()
    db.add_all([coord_role, user_role])
    await db.flush()

    coord = User(
        full_name="Coord",
        username="coord",
        password_hash=hash_password("pass"),
        role_id=coord_role.id,
        telegram_chat_id="777",
    )
    requester = User(
        full_name="Alice",
        username="alice",
        password_hash=hash_password("pass"),
        role_id=user_role.id,
    )
    db.add_all([coord, requester])

    room = Room(name="Room A")
    db.add(room)
    await db.flush()
    cabinet = Cabinet(name="Cab A", room_id=room.id)
    db.add(cabinet)
    await db.flush()
    item = Item(name="Drill", quantity_total=5, quantity_available=5, cabinet_id=cabinet.id)
    db.add(item)
    await db.flush()

    req = InventoryRequest(
        requester_id=requester.id,
        item_id=item.id,
        quantity_requested=1,
        status=RequestStatus.PENDING,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(
            _group_update(777, "coord_tg", -100888, f"/deny {req.id} not needed"),
            db,
        )

    bot.send_message.assert_called()
    last_text = bot.send_message.call_args_list[-1].kwargs["text"]
    assert "denied" in last_text.lower() or "❌" in last_text
    assert "not linked" not in last_text.lower()


@pytest.mark.asyncio
async def test_unknown_command_returns_help(db):
    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(111, "alice", "/foobar"), db)

    bot.send_message.assert_called_once()
    assert "/start" in _sent_text(bot)


# ─── Phase 2 regression tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_link_group_reply_does_not_echo_token(db):
    """Group rejection must not leak any part of the token in its reply."""
    await _seed_user(db, link_token="supersecrettoken")

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_group_update(999, "alice_tg", -100123456, "/link supersecrettoken"), db)

    text = _sent_text(bot)
    assert "supersecrettoken" not in text
    assert "supe" not in text  # no prefix either


@pytest.mark.asyncio
async def test_link_rejects_duplicate_actor(db):
    """If actor_tg_id is already linked to another user, reject without mutation."""
    from sqlalchemy import select as _select
    user_a = await _seed_user(db, telegram_chat_id="999")

    # Reuse user_a's role to avoid UNIQUE violation on roles.name
    from app.models.role import Role as _Role
    role = (await db.execute(_select(_Role).where(_Role.id == user_a.role_id))).scalar_one()

    user_b = User(
        full_name="Bob",
        username="bob",
        password_hash="x",
        role_id=role.id,
        telegram_link_token="tok_bob",
    )
    db.add(user_b)
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        # Bob's token, but actor Telegram ID is already taken by user_a
        await handle_update(_private_update(999, "bob_tg", "/link tok_bob"), db)

    await db.refresh(user_b)
    # Token must NOT be consumed
    assert user_b.telegram_link_token == "tok_bob"
    assert user_b.telegram_chat_id is None

    bot.send_message.assert_called_once()
    assert "already linked" in _sent_text(bot).lower()


@pytest.mark.asyncio
async def test_link_duplicate_does_not_consume_token(db):
    """Same as above — verifies token is fully intact after duplicate rejection."""
    from sqlalchemy import select as _select
    from app.models.role import Role as _Role

    user_a = await _seed_user(db, telegram_chat_id="777")
    role = (await db.execute(_select(_Role).where(_Role.id == user_a.role_id))).scalar_one()

    user_c = User(
        full_name="Carol",
        username="carol",
        password_hash="x",
        role_id=role.id,
        telegram_link_token="carol_tok",
    )
    db.add(user_c)
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(777, "carol_tg", "/link carol_tok"), db)

    await db.refresh(user_c)
    assert user_c.telegram_link_token == "carol_tok"


@pytest.mark.asyncio
async def test_link_missing_username_succeeds(db):
    """Link works even when Telegram user has no username set."""
    user = await _seed_user(db, link_token="tok_nouser")

    update = {
        "update_id": 1,
        "message": {
            "message_id": 100,
            "from": {"id": 888, "first_name": "NoHandle"},  # no "username" key
            "chat": {"id": 888, "type": "private"},
            "text": "/link tok_nouser",
        },
    }

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.bot.handlers.notify_account_linked", new=AsyncMock()):
        await handle_update(update, db)

    await db.refresh(user)
    assert user.telegram_chat_id == "888"
    assert user.telegram_link_token is None
    # telegram_handle unchanged (was None; no username to store)
    assert user.telegram_handle is None


@pytest.mark.asyncio
async def test_relink_same_user_updates_old_chat_id(db):
    """User previously linked from a group (negative ID) can relink from DM."""
    user = await _seed_user(db, telegram_chat_id="-100999", link_token="newtoken")

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.bot.handlers.notify_account_linked", new=AsyncMock()):
        await handle_update(_private_update(12345, "alice_real", "/link newtoken"), db)

    await db.refresh(user)
    assert user.telegram_chat_id == "12345"
    assert user.telegram_link_token is None


@pytest.mark.asyncio
async def test_overdue_group_resolves_by_from_id(db):
    """Coordinator linked by personal ID; /overdue from a group must resolve correctly."""
    role = _coord_role()
    db.add(role)
    await db.flush()
    await _seed_user(db, telegram_chat_id="555", role=role)

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_group_update(555, "coord_tg", -100888, "/overdue"), db)

    bot.send_message.assert_called_once()
    assert _sent_chat(bot) == "-100888"
    assert "not linked" not in _sent_text(bot).lower()


@pytest.mark.asyncio
async def test_myitems_bot_mentioned_command(db):
    """'/myitems@BotUsername' is correctly parsed as /myitems."""
    await _seed_user(db, telegram_chat_id="321")

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(321, "alice_tg", "/myitems@CabinetInventoryBot"), db)

    bot.send_message.assert_called_once()
    assert "not linked" not in _sent_text(bot).lower()


@pytest.mark.asyncio
async def test_malformed_update_no_from(db):
    """Update without a 'from' field (channel post) must be ignored silently."""
    update = {
        "update_id": 1,
        "message": {
            "message_id": 100,
            # no "from" key
            "chat": {"id": -100123456, "type": "channel"},
            "text": "/myitems",
        },
    }

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(update, db)

    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_link_integrity_error_handled(db):
    """Concurrent /link from same Telegram actor triggers IntegrityError — no 500, token preserved."""
    user = await _seed_user(db, link_token="race_token")

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch.object(db, "commit", side_effect=SAIntegrityError("UNIQUE", {}, Exception("dup"))):
        # Must not raise — handler must catch IntegrityError internally
        await handle_update(_private_update(999, "alice_tg", "/link race_token"), db)

    bot.send_message.assert_called_once()
    assert "already linked" in _sent_text(bot).lower()

    # Rollback was called by the handler; refresh loads fresh DB state
    await db.refresh(user)
    assert user.telegram_link_token == "race_token"  # token preserved
    assert user.telegram_chat_id is None              # no mutation committed


# ─── Prompt 2: approve/deny reliability + requester DMs ───────────────────────

async def _seed_p2_request(
    db: AsyncSession, *, requester_linked: bool = False
) -> tuple:
    """Seed coordinator (tg='777') + requester + item + pending request."""
    coord_role = _coord_role()
    user_role = _user_role()
    db.add_all([coord_role, user_role])
    await db.flush()

    coord = User(
        full_name="Coord", username="coord", password_hash=hash_password("pass"),
        role_id=coord_role.id, telegram_chat_id="777",
    )
    requester = User(
        full_name="Alice", username="alice", password_hash=hash_password("pass"),
        role_id=user_role.id,
        telegram_chat_id="888" if requester_linked else None,
    )
    db.add_all([coord, requester])

    room = Room(name="Room A")
    db.add(room)
    await db.flush()
    cabinet = Cabinet(name="Cab A", room_id=room.id)
    db.add(cabinet)
    await db.flush()
    item = Item(name="Drill", quantity_total=5, quantity_available=5, cabinet_id=cabinet.id)
    db.add(item)
    await db.flush()

    req = InventoryRequest(
        requester_id=requester.id, item_id=item.id,
        quantity_requested=1, status=RequestStatus.PENDING,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return coord, requester, item, req


@pytest.mark.asyncio
async def test_approve_commits_status_fulfilled(db):
    """cmd_approve transitions request to FULFILLED and commits."""
    coord, requester, item, req = await _seed_p2_request(db)

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_group_update(777, "coord_tg", -100888, f"/approve {req.id}"), db)

    await db.refresh(req)
    assert req.status == RequestStatus.FULFILLED


@pytest.mark.asyncio
async def test_approve_reply_shows_real_item_name(db):
    """Bot reply for a successful approval names the item, not 'Item #N'."""
    coord, requester, item, req = await _seed_p2_request(db)

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_group_update(777, "coord_tg", -100888, f"/approve {req.id}"), db)

    reply = bot.send_message.call_args_list[0].kwargs["text"]
    assert "Drill" in reply
    assert f"Item #{item.id}" not in reply


@pytest.mark.asyncio
async def test_approve_dms_linked_requester(db):
    """When requester has telegram_chat_id, notify_request_approved is called."""
    coord, requester, item, req = await _seed_p2_request(db, requester_linked=True)

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.telegram_service.notify_request_approved", new=AsyncMock()) as mock_notify:
        await handle_update(_group_update(777, "coord_tg", -100888, f"/approve {req.id}"), db)

    mock_notify.assert_awaited_once()
    a = mock_notify.call_args.args
    assert a[0] == "888"
    assert "Drill" in a[1]
    assert a[2] == req.id


@pytest.mark.asyncio
async def test_approve_already_processed_friendly_message(db):
    """Attempting to approve an already-FULFILLED request gives a friendly message."""
    coord, requester, item, req = await _seed_p2_request(db)
    req.status = RequestStatus.FULFILLED
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_group_update(777, "coord_tg", -100888, f"/approve {req.id}"), db)

    reply = _sent_text(bot)
    assert "already been processed" in reply
    assert "RequestStatus" not in reply


@pytest.mark.asyncio
async def test_deny_commits_status_denied(db):
    """cmd_deny transitions request to DENIED and commits."""
    coord, requester, item, req = await _seed_p2_request(db)

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_group_update(777, "coord_tg", -100888, f"/deny {req.id}"), db)

    await db.refresh(req)
    assert req.status == RequestStatus.DENIED


@pytest.mark.asyncio
async def test_deny_with_reason_in_reply(db):
    """Denial reason and item name both appear in the bot reply."""
    coord, requester, item, req = await _seed_p2_request(db)

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_group_update(777, "coord_tg", -100888, f"/deny {req.id} out of stock"), db)

    reply = bot.send_message.call_args_list[0].kwargs["text"]
    assert "Drill" in reply
    assert "out of stock" in reply


@pytest.mark.asyncio
async def test_deny_dms_linked_requester(db):
    """When requester has telegram_chat_id, notify_request_denied is called with reason."""
    coord, requester, item, req = await _seed_p2_request(db, requester_linked=True)

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.telegram_service.notify_request_denied", new=AsyncMock()) as mock_notify:
        await handle_update(_group_update(777, "coord_tg", -100888, f"/deny {req.id} out of stock"), db)

    mock_notify.assert_awaited_once()
    a = mock_notify.call_args.args
    assert a[0] == "888"
    assert "Drill" in a[1]
    assert a[2] == req.id
    assert a[3] == "out of stock"


@pytest.mark.asyncio
async def test_deny_already_processed_friendly_message(db):
    """Attempting to deny an already-DENIED request gives a friendly message."""
    coord, requester, item, req = await _seed_p2_request(db)
    req.status = RequestStatus.DENIED
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_group_update(777, "coord_tg", -100888, f"/deny {req.id}"), db)

    reply = _sent_text(bot)
    assert "already been processed" in reply
    assert "RequestStatus" not in reply


@pytest.mark.asyncio
async def test_approve_insufficient_stock_rolls_back(db):
    """cmd_approve with insufficient stock rolls back, sends safe message, no transaction created."""
    coord, requester, item, req = await _seed_p2_request(db)
    item.quantity_available = 0
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_group_update(777, "coord_tg", -100888, f"/approve {req.id}"), db)

    await db.refresh(req)
    assert req.status == RequestStatus.PENDING
    assert req.approver_id is None

    reply = _sent_text(bot)
    assert "❌" in reply
    assert "Error:" not in reply


@pytest.mark.asyncio
async def test_approve_bin_already_checked_out_keeps_pending(db):
    """cmd_approve for a bin request when the bin is already checked out keeps request PENDING."""
    coord_role = _coord_role()
    user_role = _user_role()
    db.add_all([coord_role, user_role])
    await db.flush()

    coord = User(
        full_name="Coord", username="coord", password_hash=hash_password("pass"),
        role_id=coord_role.id, telegram_chat_id="777",
    )
    requester = User(
        full_name="Alice", username="alice", password_hash=hash_password("pass"),
        role_id=user_role.id,
    )
    db.add_all([coord, requester])

    room = Room(name="Room A")
    db.add(room)
    await db.flush()
    cabinet = Cabinet(name="Cab A", room_id=room.id)
    db.add(cabinet)
    await db.flush()
    bin_obj = Bin(label="BinA", cabinet_id=cabinet.id)
    db.add(bin_obj)
    await db.flush()

    # Pre-existing checkout of the bin
    db.add(BinTransaction(
        bin_id=bin_obj.id, user_id=requester.id,
        processed_by_user_id=coord.id,
        status=BinTransactionStatus.CHECKED_OUT,
    ))

    req = InventoryRequest(
        requester_id=requester.id, bin_id=bin_obj.id,
        quantity_requested=1, status=RequestStatus.PENDING,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_group_update(777, "coord_tg", -100888, f"/approve {req.id}"), db)

    await db.refresh(req)
    assert req.status == RequestStatus.PENDING

    reply = _sent_text(bot)
    assert "already been processed" not in reply
    assert "❌" in reply


@pytest.mark.asyncio
async def test_approve_dm_failure_does_not_rollback(db):
    """Requester DM failure after a successful approval does not roll back the commit."""
    coord, requester, item, req = await _seed_p2_request(db, requester_linked=True)

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.telegram_service.notify_request_approved",
               new=AsyncMock(side_effect=RuntimeError("TG down"))):
        await handle_update(_group_update(777, "coord_tg", -100888, f"/approve {req.id}"), db)

    await db.refresh(req)
    assert req.status == RequestStatus.FULFILLED


@pytest.mark.asyncio
async def test_deny_dm_failure_does_not_rollback(db):
    """Requester DM failure after a successful denial does not roll back the commit."""
    coord, requester, item, req = await _seed_p2_request(db, requester_linked=True)

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.telegram_service.notify_request_denied",
               new=AsyncMock(side_effect=RuntimeError("TG down"))):
        await handle_update(_group_update(777, "coord_tg", -100888, f"/deny {req.id} no reason"), db)

    await db.refresh(req)
    assert req.status == RequestStatus.DENIED


@pytest.mark.asyncio
async def test_approve_unexpected_error_rolls_back_safe_message(db):
    """Unexpected service error in cmd_approve: rollback, safe generic message, no raw details leaked."""
    coord, requester, item, req = await _seed_p2_request(db)

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.request_service.approve_request",
               side_effect=RuntimeError("internal: db_password=secret")):
        await handle_update(_group_update(777, "coord_tg", -100888, f"/approve {req.id}"), db)

    await db.refresh(req)
    assert req.status == RequestStatus.PENDING
    assert req.approver_id is None

    reply = _sent_text(bot)
    assert "❌" in reply
    assert "db_password" not in reply
    assert "Could not process" in reply


@pytest.mark.asyncio
async def test_deny_unexpected_error_rolls_back_safe_message(db):
    """Unexpected service error in cmd_deny: rollback, safe generic message, no raw details leaked."""
    coord, requester, item, req = await _seed_p2_request(db)

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.request_service.deny_request",
               side_effect=RuntimeError("internal: auth_token=xyz")):
        await handle_update(_group_update(777, "coord_tg", -100888, f"/deny {req.id} reason"), db)

    await db.refresh(req)
    assert req.status == RequestStatus.PENDING
    assert req.approver_id is None

    reply = _sent_text(bot)
    assert "❌" in reply
    assert "auth_token" not in reply
    assert "Could not process" in reply
