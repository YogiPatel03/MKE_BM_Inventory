"""
Tests for TELEGRAM_COORDINATOR_THREAD_ID routing.

Covers:
- send_to_coordinator sends with message_thread_id when the setting is a valid integer
- send_to_coordinator omits message_thread_id when the setting is blank
- Invalid (non-integer) value falls back to no thread and does not crash
- Group topic mapping is unaffected by TELEGRAM_COORDINATOR_THREAD_ID
  (both set simultaneously; group topic must still use its own thread ID)
- Fallback fires ONLY on known thread-rejection BadRequest, not on ambiguous failures
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut

from app.services import telegram_service


def _mock_bot(message_id: int = 42):
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=message_id))
    return bot


# ─── _parse_coordinator_thread_id ────────────────────────────────────────────

def test_parse_coordinator_thread_id_returns_int_for_valid_value():
    with patch("app.services.telegram_service.settings") as ms:
        ms.telegram_coordinator_thread_id = "99"
        result = telegram_service._parse_coordinator_thread_id()
    assert result == 99


def test_parse_coordinator_thread_id_returns_none_for_blank():
    with patch("app.services.telegram_service.settings") as ms:
        ms.telegram_coordinator_thread_id = ""
        result = telegram_service._parse_coordinator_thread_id()
    assert result is None


def test_parse_coordinator_thread_id_returns_none_for_invalid_string():
    with patch("app.services.telegram_service.settings") as ms:
        ms.telegram_coordinator_thread_id = "not-a-number"
        result = telegram_service._parse_coordinator_thread_id()
    assert result is None


def test_parse_coordinator_thread_id_returns_none_for_float_string():
    with patch("app.services.telegram_service.settings") as ms:
        ms.telegram_coordinator_thread_id = "3.14"
        result = telegram_service._parse_coordinator_thread_id()
    assert result is None


def test_parse_coordinator_thread_id_returns_none_for_zero():
    with patch("app.services.telegram_service.settings") as ms:
        ms.telegram_coordinator_thread_id = "0"
        result = telegram_service._parse_coordinator_thread_id()
    assert result is None


def test_parse_coordinator_thread_id_returns_none_for_negative():
    with patch("app.services.telegram_service.settings") as ms:
        ms.telegram_coordinator_thread_id = "-5"
        result = telegram_service._parse_coordinator_thread_id()
    assert result is None


# ─── _is_invalid_thread_error ────────────────────────────────────────────────

def test_is_invalid_thread_error_true_for_thread_not_found():
    err = BadRequest("Message thread not found")
    assert telegram_service._is_invalid_thread_error(err) is True


def test_is_invalid_thread_error_true_for_topic_closed():
    # Telegram sends "TOPIC_CLOSED"; PTB strips prefix and capitalizes → "Topic_closed"
    err = BadRequest("Topic_closed")
    assert telegram_service._is_invalid_thread_error(err) is True


def test_is_invalid_thread_error_true_for_topic_deleted():
    err = BadRequest("Topic_deleted")
    assert telegram_service._is_invalid_thread_error(err) is True


def test_is_invalid_thread_error_false_for_generic_badrequest():
    err = BadRequest("Chat not found")
    assert telegram_service._is_invalid_thread_error(err) is False


def test_is_invalid_thread_error_false_for_network_error():
    # NetworkError is NOT BadRequest (the inheritance is the other way: BadRequest IS-A NetworkError)
    err = NetworkError("connection refused")
    assert telegram_service._is_invalid_thread_error(err) is False


def test_is_invalid_thread_error_false_for_none():
    assert telegram_service._is_invalid_thread_error(None) is False


def test_is_invalid_thread_error_false_for_runtime_error():
    assert telegram_service._is_invalid_thread_error(RuntimeError("boom")) is False


# ─── send_to_coordinator ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_to_coordinator_uses_thread_id_when_set():
    """When TELEGRAM_COORDINATOR_THREAD_ID is set, message_thread_id is forwarded to the bot."""
    bot = _mock_bot()
    with patch("app.services.telegram_service.settings") as ms, \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        ms.telegram_coordinator_chat_id = "-100111"
        ms.telegram_coordinator_thread_id = "55"
        ms.telegram_enabled = True
        result = await telegram_service.send_to_coordinator("hello coordinator topic")

    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == "-100111"
    assert kwargs["message_thread_id"] == 55
    assert result == 42


@pytest.mark.asyncio
async def test_send_to_coordinator_omits_thread_id_when_blank():
    """When TELEGRAM_COORDINATOR_THREAD_ID is blank, message_thread_id is not sent."""
    bot = _mock_bot()
    with patch("app.services.telegram_service.settings") as ms, \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        ms.telegram_coordinator_chat_id = "-100111"
        ms.telegram_coordinator_thread_id = ""
        ms.telegram_enabled = True
        result = await telegram_service.send_to_coordinator("hello general")

    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == "-100111"
    assert "message_thread_id" not in kwargs
    assert result == 42


@pytest.mark.asyncio
async def test_send_to_coordinator_falls_back_gracefully_on_invalid_thread_id():
    """Invalid TELEGRAM_COORDINATOR_THREAD_ID falls back to no thread without crashing."""
    bot = _mock_bot()
    with patch("app.services.telegram_service.settings") as ms, \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        ms.telegram_coordinator_chat_id = "-100111"
        ms.telegram_coordinator_thread_id = "not-an-int"
        ms.telegram_enabled = True
        result = await telegram_service.send_to_coordinator("should still send")

    assert bot.send_message.called, "Message must still be sent despite invalid thread ID"
    kwargs = bot.send_message.call_args.kwargs
    assert "message_thread_id" not in kwargs
    assert result == 42


@pytest.mark.asyncio
async def test_send_to_coordinator_returns_none_when_no_chat_id():
    """send_to_coordinator returns None without sending when coordinator chat is unset."""
    with patch("app.services.telegram_service.settings") as ms:
        ms.telegram_coordinator_chat_id = ""
        ms.telegram_coordinator_thread_id = "55"
        result = await telegram_service.send_to_coordinator("nobody home")
    assert result is None


@pytest.mark.asyncio
async def test_send_to_coordinator_no_retry_when_no_thread_configured():
    """When no thread ID is configured, send_to_coordinator calls _send exactly once."""
    with patch("app.services.telegram_service.settings") as ms, \
         patch("app.services.telegram_service._send", new_callable=AsyncMock) as mock_send:
        ms.telegram_coordinator_chat_id = "-100111"
        ms.telegram_coordinator_thread_id = ""
        mock_send.return_value = 42
        result = await telegram_service.send_to_coordinator("single send")

    assert mock_send.call_count == 1
    assert result == 42


@pytest.mark.asyncio
async def test_send_to_coordinator_falls_back_for_zero_thread_id():
    """TELEGRAM_COORDINATOR_THREAD_ID=0 is treated as invalid; sends to General without thread."""
    with patch("app.services.telegram_service.settings") as ms, \
         patch("app.services.telegram_service._send", new_callable=AsyncMock) as mock_send:
        ms.telegram_coordinator_chat_id = "-100111"
        ms.telegram_coordinator_thread_id = "0"
        mock_send.return_value = 42
        result = await telegram_service.send_to_coordinator("zero thread test")

    assert mock_send.call_count == 1
    assert "message_thread_id" not in mock_send.call_args.kwargs
    assert result == 42


@pytest.mark.asyncio
async def test_send_to_coordinator_falls_back_for_negative_thread_id():
    """TELEGRAM_COORDINATOR_THREAD_ID=-5 is treated as invalid; sends to General without thread."""
    with patch("app.services.telegram_service.settings") as ms, \
         patch("app.services.telegram_service._send", new_callable=AsyncMock) as mock_send:
        ms.telegram_coordinator_chat_id = "-100111"
        ms.telegram_coordinator_thread_id = "-5"
        mock_send.return_value = 42
        result = await telegram_service.send_to_coordinator("negative thread test")

    assert mock_send.call_count == 1
    assert "message_thread_id" not in mock_send.call_args.kwargs
    assert result == 42


# ─── Scoped fallback: known thread-rejection errors ──────────────────────────

@pytest.mark.asyncio
async def test_send_to_coordinator_falls_back_on_known_invalid_thread_badrequest():
    """
    A BadRequest with 'Message thread not found' triggers exactly one retry to General
    and returns the fallback message_id. This drives the error through bot.send_message
    so the _is_invalid_thread_error classifier is exercised on the real exception.
    """
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=[
        BadRequest("Message thread not found"),  # topic attempt
        MagicMock(message_id=77),               # General fallback
    ])
    with patch("app.services.telegram_service.settings") as ms, \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        ms.telegram_coordinator_chat_id = "-100111"
        ms.telegram_coordinator_thread_id = "55"
        ms.telegram_enabled = True
        result = await telegram_service.send_to_coordinator("fallback test")

    assert bot.send_message.call_count == 2, "Must retry once on known invalid-thread error"
    first_call = bot.send_message.call_args_list[0]
    second_call = bot.send_message.call_args_list[1]
    assert first_call.kwargs["message_thread_id"] == 55
    assert "message_thread_id" not in second_call.kwargs
    assert result == 77


@pytest.mark.asyncio
async def test_send_to_coordinator_falls_back_on_topic_closed():
    """TOPIC_CLOSED (PTB-normalized to 'Topic_closed') also triggers the fallback."""
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=[
        BadRequest("Topic_closed"),
        MagicMock(message_id=88),
    ])
    with patch("app.services.telegram_service.settings") as ms, \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        ms.telegram_coordinator_chat_id = "-100111"
        ms.telegram_coordinator_thread_id = "55"
        ms.telegram_enabled = True
        result = await telegram_service.send_to_coordinator("topic closed test")

    assert bot.send_message.call_count == 2
    assert result == 88


# ─── Scoped fallback: ambiguous failures must NOT retry ──────────────────────

@pytest.mark.asyncio
async def test_send_to_coordinator_no_fallback_on_network_error():
    """Plain NetworkError on topic send must NOT trigger a fallback — returns None."""
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=NetworkError("connection refused"))
    with patch("app.services.telegram_service.settings") as ms, \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        ms.telegram_coordinator_chat_id = "-100111"
        ms.telegram_coordinator_thread_id = "55"
        ms.telegram_enabled = True
        result = await telegram_service.send_to_coordinator("network error test")

    assert bot.send_message.call_count == 1, "Must not retry on NetworkError"
    assert result is None


@pytest.mark.asyncio
async def test_send_to_coordinator_no_fallback_on_timed_out():
    """TimedOut on topic send must NOT trigger a fallback — returns None."""
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=TimedOut())
    with patch("app.services.telegram_service.settings") as ms, \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        ms.telegram_coordinator_chat_id = "-100111"
        ms.telegram_coordinator_thread_id = "55"
        ms.telegram_enabled = True
        result = await telegram_service.send_to_coordinator("timeout test")

    assert bot.send_message.call_count == 1, "Must not retry on TimedOut"
    assert result is None


@pytest.mark.asyncio
async def test_send_to_coordinator_no_fallback_on_retry_after():
    """RetryAfter (rate-limit) on topic send must NOT trigger a fallback — returns None."""
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=RetryAfter(retry_after=30))
    with patch("app.services.telegram_service.settings") as ms, \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        ms.telegram_coordinator_chat_id = "-100111"
        ms.telegram_coordinator_thread_id = "55"
        ms.telegram_enabled = True
        result = await telegram_service.send_to_coordinator("rate limit test")

    assert bot.send_message.call_count == 1, "Must not retry on RetryAfter"
    assert result is None


@pytest.mark.asyncio
async def test_send_to_coordinator_no_fallback_on_generic_badrequest():
    """A BadRequest unrelated to thread/topic must NOT trigger a fallback — returns None."""
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=BadRequest("Chat not found"))
    with patch("app.services.telegram_service.settings") as ms, \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        ms.telegram_coordinator_chat_id = "-100111"
        ms.telegram_coordinator_thread_id = "55"
        ms.telegram_enabled = True
        result = await telegram_service.send_to_coordinator("generic badrequest test")

    assert bot.send_message.call_count == 1, "Must not retry on generic BadRequest"
    assert result is None


@pytest.mark.asyncio
async def test_send_to_coordinator_no_fallback_on_unexpected_exception():
    """An unexpected non-Telegram exception must NOT trigger a fallback — returns None."""
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=RuntimeError("unexpected boom"))
    with patch("app.services.telegram_service.settings") as ms, \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        ms.telegram_coordinator_chat_id = "-100111"
        ms.telegram_coordinator_thread_id = "55"
        ms.telegram_enabled = True
        result = await telegram_service.send_to_coordinator("unexpected exception test")

    assert bot.send_message.call_count == 1, "Must not retry on unexpected exception"
    assert result is None


# ─── message_id preservation ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_to_coordinator_returns_topic_message_id_on_success():
    """Successful topic send returns the topic message_id, not a fallback id."""
    bot = _mock_bot(message_id=99)
    with patch("app.services.telegram_service.settings") as ms, \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        ms.telegram_coordinator_chat_id = "-100111"
        ms.telegram_coordinator_thread_id = "55"
        ms.telegram_enabled = True
        result = await telegram_service.send_to_coordinator("success test")

    assert result == 99
    assert bot.send_message.call_count == 1


# ─── Group topic isolation ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_group_topic_uses_its_own_thread_id_when_coordinator_thread_also_set():
    """
    When both TELEGRAM_COORDINATOR_THREAD_ID and TELEGRAM_GROUP_TOPIC_THREAD_IDS are set,
    send_to_group_topic must use the group's own thread ID — not the coordinator thread.
    """
    bot = _mock_bot()
    mapping = json.dumps({"GROUP_1": 34})
    with patch("app.services.telegram_service.settings") as ms, \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        ms.telegram_coordinator_chat_id = "-100999"
        ms.telegram_coordinator_thread_id = "99"   # coordinator topic
        ms.telegram_group_topic_thread_ids = mapping
        ms.telegram_enabled = True
        await telegram_service.send_to_group_topic("GROUP_1", "group 1 checklist")

    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == "-100999"
    assert kwargs["message_thread_id"] == 34, (
        "Group topic must use its own thread (34), not the coordinator thread (99)"
    )
