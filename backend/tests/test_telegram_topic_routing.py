"""
Tests for Telegram topic/forum routing additions (Prompt 3).

Covers:
- _send passes message_thread_id to bot.send_message when provided
- _send omits message_thread_id when not provided (old behaviour preserved)
- Valid JSON topic mapping routes GROUP_1 to the correct thread ID
- Invalid/missing JSON does not crash (returns empty mapping)
- /whereami prints correct chat_id and message_thread_id in a topic
- /whereami works in a plain DM (no thread)
- /whoami resolves linked user by message.from.id
- /whoami for an unlinked user explains how to link
- /link in a group/topic is rejected without consuming the token
- /link group rejection does not echo any part of the submitted token
- /link in DM succeeds and stores message.from.id (actor_telegram_id)
- User lookup uses message.from.id, not group chat.id
- Personal DMs use user.telegram_chat_id and are not sent to topics
- Coordinator notifications can carry message_thread_id when called with one
- send_to_group_topic routes to correct thread_id from mapping
- send_to_group_topic falls back to coordinator chat when group has no mapping
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import handle_update
from app.core.security import hash_password
from app.models.role import Role
from app.models.user import User


# ─── Payload factories ───────────────────────────────────────────────────────

def _private_update(user_id: int, username: str, text: str) -> dict:
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
    return {
        "update_id": 1,
        "message": {
            "message_id": 100,
            "from": {"id": user_id, "username": username, "first_name": "Test"},
            "chat": {"id": group_id, "type": "group"},
            "text": text,
        },
    }


def _topic_update(user_id: int, username: str, group_id: int, thread_id: int, text: str) -> dict:
    """Supergroup topic update: same chat_id as group, plus message_thread_id."""
    return {
        "update_id": 1,
        "message": {
            "message_id": 100,
            "from": {"id": user_id, "username": username, "first_name": "Test"},
            "chat": {"id": group_id, "type": "supergroup"},
            "message_thread_id": thread_id,
            "text": text,
        },
    }


# ─── Seed helpers ────────────────────────────────────────────────────────────

def _user_role(**flags) -> Role:
    defaults = dict(
        can_manage_inventory=False, can_manage_cabinets=False, can_manage_bins=False,
        can_manage_users=False, can_process_any_transaction=False,
        can_view_all_transactions=False, can_view_audit_logs=False, can_approve_requests=False,
    )
    defaults.update(flags)
    return Role(name=f"TOPIC_USER_{id(flags)}", **defaults)


async def _seed_user(
    db: AsyncSession,
    *,
    telegram_chat_id: str | None = None,
    link_token: str | None = None,
    role: Role | None = None,
    username: str = "testuser",
    group_name: str | None = None,
) -> User:
    if role is None:
        role = _user_role()
        db.add(role)
        await db.flush()
    user = User(
        full_name="Test User",
        username=username,
        password_hash=hash_password("pass"),
        role_id=role.id,
        telegram_chat_id=telegram_chat_id,
        telegram_link_token=link_token,
        group_name=group_name,
    )
    db.add(user)
    await db.commit()
    return user


def _mock_bot():
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    return bot


def _sent_kwargs(mock_bot, call_index: int = -1) -> dict:
    return mock_bot.send_message.call_args_list[call_index].kwargs


# ─── telegram_service._send thread_id passthrough ────────────────────────────

@pytest.mark.asyncio
async def test_send_passes_thread_id_when_provided():
    """_send includes message_thread_id in the bot.send_message call when given."""
    from app.services import telegram_service

    bot = _mock_bot()
    with patch("app.services.telegram_service.get_bot", return_value=bot):
        await telegram_service._send("123", "hello", message_thread_id=42)

    call_kwargs = bot.send_message.call_args.kwargs
    assert call_kwargs.get("message_thread_id") == 42


@pytest.mark.asyncio
async def test_send_omits_thread_id_when_not_provided():
    """_send does not include message_thread_id when called without it."""
    from app.services import telegram_service

    bot = _mock_bot()
    with patch("app.services.telegram_service.get_bot", return_value=bot):
        await telegram_service._send("123", "hello")

    call_kwargs = bot.send_message.call_args.kwargs
    assert "message_thread_id" not in call_kwargs


@pytest.mark.asyncio
async def test_send_omits_thread_id_when_none():
    """_send does not include message_thread_id when explicitly passed None."""
    from app.services import telegram_service

    bot = _mock_bot()
    with patch("app.services.telegram_service.get_bot", return_value=bot):
        await telegram_service._send("123", "hello", message_thread_id=None)

    call_kwargs = bot.send_message.call_args.kwargs
    assert "message_thread_id" not in call_kwargs


# ─── Topic mapping helpers ────────────────────────────────────────────────────

def test_valid_json_mapping_routes_group1():
    """Valid JSON mapping returns the correct thread ID for GROUP_1."""
    from app.services.telegram_service import get_thread_id_for_group

    mapping = json.dumps({"SHISHU_MANDAL": 12, "GROUP_1": 34, "GROUP_2": 56, "GROUP_3": 78})
    with patch("app.services.telegram_service.settings") as mock_settings:
        mock_settings.telegram_group_topic_thread_ids = mapping
        assert get_thread_id_for_group("GROUP_1") == 34
        assert get_thread_id_for_group("SHISHU_MANDAL") == 12
        assert get_thread_id_for_group("GROUP_3") == 78


def test_invalid_json_mapping_does_not_crash():
    """Invalid JSON in TELEGRAM_GROUP_TOPIC_THREAD_IDS returns empty dict — no exception."""
    from app.services.telegram_service import get_thread_id_for_group

    with patch("app.services.telegram_service.settings") as mock_settings:
        mock_settings.telegram_group_topic_thread_ids = "not valid json {"
        result = get_thread_id_for_group("GROUP_1")
    assert result is None


def test_missing_mapping_returns_none():
    """Empty TELEGRAM_GROUP_TOPIC_THREAD_IDS returns None for any group."""
    from app.services.telegram_service import get_thread_id_for_group

    with patch("app.services.telegram_service.settings") as mock_settings:
        mock_settings.telegram_group_topic_thread_ids = ""
        assert get_thread_id_for_group("GROUP_1") is None


def test_non_object_json_returns_empty():
    """JSON that is valid but not an object (e.g. a list) returns empty dict."""
    from app.services.telegram_service import get_thread_id_for_group

    with patch("app.services.telegram_service.settings") as mock_settings:
        mock_settings.telegram_group_topic_thread_ids = "[1, 2, 3]"
        assert get_thread_id_for_group("GROUP_1") is None


def test_get_group_for_thread_id_reverse_lookup():
    """get_group_for_thread_id finds the group name from a known thread ID."""
    from app.services.telegram_service import get_group_for_thread_id

    mapping = json.dumps({"SHISHU_MANDAL": 12, "GROUP_1": 34})
    with patch("app.services.telegram_service.settings") as mock_settings:
        mock_settings.telegram_group_topic_thread_ids = mapping
        assert get_group_for_thread_id(34) == "GROUP_1"
        assert get_group_for_thread_id(12) == "SHISHU_MANDAL"
        assert get_group_for_thread_id(999) is None


# ─── send_to_group_topic ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_to_group_topic_uses_thread_id():
    """send_to_group_topic passes the correct thread_id for a mapped group."""
    from app.services.telegram_service import send_to_group_topic

    mapping = json.dumps({"GROUP_1": 34})
    bot = _mock_bot()
    with patch("app.services.telegram_service.settings") as mock_settings, \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        mock_settings.telegram_coordinator_chat_id = "-100999"
        mock_settings.telegram_group_topic_thread_ids = mapping
        mock_settings.telegram_enabled = True
        await send_to_group_topic("GROUP_1", "hello group 1")

    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == "-100999"
    assert kwargs["message_thread_id"] == 34


@pytest.mark.asyncio
async def test_send_to_group_topic_fallback_when_no_mapping():
    """send_to_group_topic falls back to coordinator chat (no thread) when group is unmapped."""
    from app.services.telegram_service import send_to_group_topic

    bot = _mock_bot()
    with patch("app.services.telegram_service.settings") as mock_settings, \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        mock_settings.telegram_coordinator_chat_id = "-100999"
        mock_settings.telegram_group_topic_thread_ids = ""
        mock_settings.telegram_enabled = True
        await send_to_group_topic("GROUP_2", "fallback message")

    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == "-100999"
    assert "message_thread_id" not in kwargs


@pytest.mark.asyncio
async def test_send_to_group_topic_returns_none_when_no_coordinator():
    """send_to_group_topic returns None when TELEGRAM_COORDINATOR_CHAT_ID is not set."""
    from app.services.telegram_service import send_to_group_topic

    with patch("app.services.telegram_service.settings") as mock_settings:
        mock_settings.telegram_coordinator_chat_id = ""
        mock_settings.telegram_group_topic_thread_ids = ""
        result = await send_to_group_topic("GROUP_1", "hello")

    assert result is None


# ─── /whereami ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_whereami_in_topic_prints_chat_and_thread_ids(db):
    """Inside a topic, /whereami prints chat_id and message_thread_id."""
    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.telegram_service.settings") as _ms:
        _ms.telegram_group_topic_thread_ids = ""
        await handle_update(
            _topic_update(user_id=111, username="alice", group_id=-100555, thread_id=42, text="/whereami"),
            db,
        )

    bot.send_message.assert_called_once()
    kwargs = _sent_kwargs(bot)
    text = kwargs["text"]
    assert "-100555" in text, "chat_id must appear in /whereami output"
    assert "42" in text, "message_thread_id must appear in /whereami output"
    assert "111" in text, "actor_telegram_id must appear in /whereami output"
    # Reply stays in the same topic
    assert kwargs.get("message_thread_id") == 42


@pytest.mark.asyncio
async def test_whereami_in_dm_shows_no_thread(db):
    """/whereami in a DM shows chat_id but no topic thread."""
    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.telegram_service.settings") as _ms:
        _ms.telegram_group_topic_thread_ids = ""
        await handle_update(_private_update(111, "alice", "/whereami"), db)

    bot.send_message.assert_called_once()
    kwargs = _sent_kwargs(bot)
    text = kwargs["text"]
    assert "111" in text
    assert "not a topic" in text
    assert kwargs.get("message_thread_id") is None


@pytest.mark.asyncio
async def test_whereami_shows_mapped_group_hint(db):
    """/whereami in a mapped topic hints the group name."""
    mapping = json.dumps({"GROUP_1": 34})
    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.telegram_service.settings") as _ms:
        _ms.telegram_group_topic_thread_ids = mapping
        await handle_update(
            _topic_update(user_id=111, username="alice", group_id=-100555, thread_id=34, text="/whereami"),
            db,
        )

    text = _sent_kwargs(bot)["text"]
    assert "GROUP_1" in text


# ─── /whoami ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_whoami_resolves_linked_user_by_from_id(db):
    """/whoami shows the linked user resolved via message.from.id."""
    await _seed_user(db, telegram_chat_id="999", username="alice_whoami")

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(999, "alice_tg", "/whoami"), db)

    bot.send_message.assert_called_once()
    text = _sent_kwargs(bot)["text"]
    assert "alice_whoami" in text
    assert "not linked" not in text.lower()


@pytest.mark.asyncio
async def test_whoami_unlinked_explains_how_to_link(db):
    """/whoami for an unlinked Telegram ID explains the linking flow."""
    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(12345, "nobody", "/whoami"), db)

    bot.send_message.assert_called_once()
    text = _sent_kwargs(bot)["text"]
    assert "/link" in text or "Settings" in text


@pytest.mark.asyncio
async def test_whoami_in_topic_uses_from_id_not_group_chat_id(db):
    """/whoami in a topic resolves by from.id, not the group's chat.id."""
    # User linked to personal ID 999; group chat_id is -100555
    await _seed_user(db, telegram_chat_id="999", username="alice_topic_who")

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(
            _topic_update(user_id=999, username="alice_tg", group_id=-100555, thread_id=42, text="/whoami"),
            db,
        )

    text = _sent_kwargs(bot)["text"]
    assert "alice_topic_who" in text
    assert "not linked" not in text.lower()


# ─── /link DM-only enforcement ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_link_in_topic_rejected_token_not_consumed(db):
    """/link inside a forum topic is rejected; token must not be consumed."""
    user = await _seed_user(db, link_token="topic_token_xyz")

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(
            _topic_update(user_id=999, username="u", group_id=-100555, thread_id=42, text="/link topic_token_xyz"),
            db,
        )

    await db.refresh(user)
    assert user.telegram_link_token == "topic_token_xyz", "Token must not be consumed in topic"
    assert user.telegram_chat_id is None


@pytest.mark.asyncio
async def test_link_in_topic_does_not_echo_token(db):
    """/link rejection in a topic must not echo any part of the submitted token."""
    await _seed_user(db, link_token="supersecret42")

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(
            _topic_update(user_id=999, username="u", group_id=-100555, thread_id=7, text="/link supersecret42"),
            db,
        )

    text = _sent_kwargs(bot)["text"]
    assert "supersecret42" not in text
    assert "supersec" not in text


@pytest.mark.asyncio
async def test_link_in_group_does_not_echo_token(db):
    """/link rejection in a plain group must not echo any part of the submitted token."""
    await _seed_user(db, link_token="anothersecret99")

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_group_update(999, "u", -100555, "/link anothersecret99"), db)

    text = _sent_kwargs(bot)["text"]
    assert "anothersecret99" not in text


@pytest.mark.asyncio
async def test_link_in_dm_stores_from_id(db):
    """/link in a DM succeeds and stores actor_telegram_id (message.from.id)."""
    user = await _seed_user(db, link_token="dm_tok_1")

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.bot.handlers.notify_account_linked", new=AsyncMock()):
        await handle_update(_private_update(12345, "alice_dm", "/link dm_tok_1"), db)

    await db.refresh(user)
    assert user.telegram_chat_id == "12345"
    assert user.telegram_link_token is None


# ─── User identity by from.id in topics ──────────────────────────────────────

@pytest.mark.asyncio
async def test_myitems_in_topic_resolves_by_from_id_not_group_id(db):
    """/myitems in a topic resolves user by from.id, replies in the topic."""
    await _seed_user(db, telegram_chat_id="999", username="alice_topic")

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(
            _topic_update(user_id=999, username="alice_tg", group_id=-100555, thread_id=42, text="/myitems"),
            db,
        )

    bot.send_message.assert_called_once()
    kwargs = _sent_kwargs(bot)
    # Reply goes to the group chat (not to the user's personal chat)
    assert str(kwargs["chat_id"]) == "-100555"
    # Reply stays in the topic
    assert kwargs.get("message_thread_id") == 42
    # User was found — no "not linked" error
    assert "not linked" not in kwargs["text"].lower()


# ─── Personal DMs not rerouted into topics ───────────────────────────────────

@pytest.mark.asyncio
async def test_personal_dm_not_sent_to_topic():
    """send_user_dm always goes to user.telegram_chat_id (personal DM), never a topic."""
    from app.services.telegram_service import send_user_dm

    user = MagicMock()
    user.telegram_chat_id = "personal_99"
    user.id = 1

    bot = _mock_bot()
    with patch("app.services.telegram_service.get_bot", return_value=bot):
        await send_user_dm(user, "private message")

    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == "personal_99"
    assert "message_thread_id" not in kwargs


# ─── Malformed update hardening ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_malformed_update_from_but_no_chat(db):
    """Update with 'from' but no 'chat' is ignored silently — no send, no exception."""
    update = {
        "update_id": 1,
        "message": {
            "message_id": 100,
            "from": {"id": 111, "username": "alice"},
            # no "chat" key
            "text": "/whereami",
        },
    }
    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(update, db)
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_malformed_update_chat_without_id(db):
    """Update with a 'chat' object missing 'id' is ignored silently — no send, no exception."""
    update = {
        "update_id": 1,
        "message": {
            "message_id": 100,
            "from": {"id": 111, "username": "alice"},
            "chat": {"type": "group"},  # no "id"
            "text": "/whereami",
        },
    }
    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(update, db)
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_malformed_update_from_without_id(db):
    """Update with a 'from' object missing 'id' is ignored silently — no send, no exception."""
    update = {
        "update_id": 1,
        "message": {
            "message_id": 100,
            "from": {"username": "alice"},  # no "id"
            "chat": {"id": -100555, "type": "group"},
            "text": "/whereami",
        },
    }
    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(update, db)
    bot.send_message.assert_not_called()


# ─── handlers._send thread_id passthrough ────────────────────────────────────

@pytest.mark.asyncio
async def test_handlers_send_passes_thread_id():
    """handlers._send passes message_thread_id to bot.send_message."""
    from app.bot.handlers import _send as handlers_send

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handlers_send("-100555", "test", message_thread_id=77)

    kwargs = bot.send_message.call_args.kwargs
    assert kwargs.get("message_thread_id") == 77


@pytest.mark.asyncio
async def test_handlers_send_omits_thread_id_by_default():
    """handlers._send omits message_thread_id when not provided."""
    from app.bot.handlers import _send as handlers_send

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handlers_send("-100555", "test")

    kwargs = bot.send_message.call_args.kwargs
    assert "message_thread_id" not in kwargs
