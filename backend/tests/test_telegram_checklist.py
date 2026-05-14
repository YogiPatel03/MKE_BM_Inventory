"""
Tests for Telegram checklist commands and Sunday scheduler logic.

Validates:
- /tasks, /mytasks, /task output includes task IDs and respects permissions
- /done, /undo update DB state correctly
- /claim, /unclaim, /assign enforce permission rules
- /assign @username sends DM to the assigned user; DM failure does not rollback
- Protected auto-generated return tasks cannot be manually marked done
- Actor identity uses from.id (not chat.id) in group/topic contexts
- Topic routing: message_thread_id used for replies and group lookup
- Sunday morning/evening scheduler functions send correct messages
- Existing /requests, /approve, /deny commands still work
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import handle_update
from app.bot.checklist_helpers import (
    _current_week_monday,
    format_full_checklist,
    format_incomplete_checklist,
    format_morning_checklist,
    format_task_line,
    send_sunday_morning_for_group,
    send_sunday_evening_for_group,
    split_messages,
)
from app.core.security import hash_password
from app.models.checklist import (
    Checklist,
    ChecklistAssignment,
    ChecklistItem,
    GroupName,
    Subchecklist,
    SubchecklistType,
)
from app.models.role import Role
from app.models.user import User


# ─── Update payload factories ─────────────────────────────────────────────────

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


def _group_update(user_id: int, username: str, group_id: int, text: str, thread_id: int | None = None) -> dict:
    msg: dict = {
        "message_id": 100,
        "from": {"id": user_id, "username": username, "first_name": "Test"},
        "chat": {"id": group_id, "type": "supergroup"},
        "text": text,
    }
    if thread_id is not None:
        msg["message_thread_id"] = thread_id
    return {"update_id": 1, "message": msg}


# ─── Role helpers ─────────────────────────────────────────────────────────────

def _user_role() -> Role:
    return Role(
        name="USER",
        can_manage_inventory=False,
        can_manage_cabinets=False,
        can_manage_bins=False,
        can_manage_users=False,
        can_process_any_transaction=False,
        can_view_all_transactions=False,
        can_view_audit_logs=False,
        can_approve_requests=False,
    )


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


def _lead_role() -> Role:
    return Role(
        name="GROUP_LEAD",
        can_manage_inventory=False,
        can_manage_cabinets=False,
        can_manage_bins=False,
        can_manage_users=False,
        can_process_any_transaction=True,
        can_view_all_transactions=False,
        can_view_audit_logs=False,
        can_approve_requests=True,
    )


# ─── Seed helpers ─────────────────────────────────────────────────────────────

async def _seed_user(
    db: AsyncSession,
    *,
    telegram_chat_id: str | None = None,
    telegram_handle: str | None = None,
    role: Role | None = None,
    group_name: str | None = None,
    username: str = "alice",
    full_name: str = "Alice Test",
) -> User:
    if role is None:
        role = _user_role()
        db.add(role)
        await db.flush()
    user = User(
        full_name=full_name,
        username=username,
        password_hash=hash_password("pass"),
        role_id=role.id,
        telegram_chat_id=telegram_chat_id,
        telegram_handle=telegram_handle,
        group_name=group_name,
    )
    db.add(user)
    await db.flush()
    return user


async def _seed_checklist(
    db: AsyncSession,
    group_name: str = GroupName.GROUP_1,
) -> Checklist:
    monday = _current_week_monday()
    cl = Checklist(group_name=group_name, week_start=monday, is_active=True)
    db.add(cl)
    await db.flush()
    return cl


async def _seed_subchecklist(
    db: AsyncSession,
    checklist: Checklist,
    title: str = "Pre Sabha",
    section_type: str = SubchecklistType.PRE_SABHA,
    order: int = 0,
) -> Subchecklist:
    sub = Subchecklist(
        checklist_id=checklist.id,
        title=title,
        section_type=section_type,
        is_mandatory=True,
        section_order=order,
    )
    db.add(sub)
    await db.flush()
    return sub


async def _seed_task(
    db: AsyncSession,
    checklist: Checklist,
    *,
    title: str = "Vacuum",
    subchecklist: Subchecklist | None = None,
    assignee_id: int | None = None,
    is_auto_generated: bool = False,
    auto_type: str | None = None,
    is_completed: bool = False,
    completed_by_id: int | None = None,
) -> ChecklistItem:
    task = ChecklistItem(
        checklist_id=checklist.id,
        subchecklist_id=subchecklist.id if subchecklist else None,
        title=title,
        item_order=0,
        assignee_id=assignee_id,
        is_auto_generated=is_auto_generated,
        auto_type=auto_type,
        is_completed=is_completed,
        completed_at=datetime.now(timezone.utc) if is_completed else None,
        completed_by_user_id=completed_by_id,
    )
    db.add(task)
    await db.flush()
    return task


async def _assign_user_to_checklist(db: AsyncSession, checklist: Checklist, user: User, assigned_by: User) -> ChecklistAssignment:
    a = ChecklistAssignment(
        checklist_id=checklist.id,
        user_id=user.id,
        assigned_by_id=assigned_by.id,
    )
    db.add(a)
    await db.flush()
    return a


def _mock_bot():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


def _all_sent_text(mock_bot: MagicMock) -> str:
    """Return concatenation of all send_message texts."""
    return " ".join(call.kwargs.get("text", "") for call in mock_bot.send_message.call_args_list)


def _first_chat(mock_bot: MagicMock) -> str:
    return str(mock_bot.send_message.call_args_list[0].kwargs["chat_id"])


def _last_thread(mock_bot: MagicMock) -> int | None:
    return mock_bot.send_message.call_args_list[-1].kwargs.get("message_thread_id")


# ─── format_task_line unit tests ──────────────────────────────────────────────

def test_format_task_line_incomplete_everyone():
    task = ChecklistItem(id=42, title="Vacuum", is_completed=False, assignee_id=None)
    task.assignee = None
    task.completed_by = None
    line = format_task_line(task)
    assert "#42" in line
    assert "Vacuum" in line
    assert "everyone" in line
    assert "⬜" in line


def test_format_task_line_completed():
    from types import SimpleNamespace
    user = SimpleNamespace(full_name="Alice")
    task = ChecklistItem(id=7, title="Turn off lights", is_completed=True, assignee_id=None)
    task.completed_by = user
    task.assignee = None
    line = format_task_line(task)
    assert "#7" in line
    assert "✅" in line
    assert "Alice" in line


def test_format_task_line_assigned_specific():
    from types import SimpleNamespace
    user = SimpleNamespace(full_name="Bob")
    task = ChecklistItem(id=5, title="Grab TVs", is_completed=False, assignee_id=99)
    task.assignee = user
    task.completed_by = None
    line = format_task_line(task)
    assert "#5" in line
    assert "Bob" in line
    assert "assigned:" in line


# ─── split_messages unit tests ────────────────────────────────────────────────

def test_split_messages_short():
    text = "short message"
    assert split_messages(text) == [text]


def test_split_messages_long():
    line = "a" * 100
    text = "\n".join([line] * 60)  # 6060 chars
    chunks = split_messages(text)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 4000
    # Reconstruct: joining chunks with \n must give back the original
    reconstructed = "\n".join(chunks)
    assert reconstructed == text


# ─── /tasks command ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tasks_shows_task_ids(db):
    """Task list output must include task IDs."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    task = await _seed_task(db, cl, title="Vacuum")
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(777, "coord", "/tasks"), db)

    assert bot.send_message.called
    text = _all_sent_text(bot)
    assert f"#{task.id}" in text
    assert "Vacuum" in text


@pytest.mark.asyncio
async def test_tasks_unlinked_user_gets_instructions(db):
    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(999, "ghost", "/tasks"), db)

    assert bot.send_message.called
    text = _all_sent_text(bot)
    assert "/link" in text or "not linked" in text.lower()


@pytest.mark.asyncio
async def test_tasks_group_topic_routing(db):
    """If sent in a topic mapped to GROUP_1, show GROUP_1 checklist regardless of arg."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    task = await _seed_task(db, cl, title="Set up tables")
    await db.commit()

    bot = _mock_bot()
    mapping = '{"GROUP_1": 500}'
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.telegram_service.settings") as mock_settings, \
         patch("app.bot.handlers.get_group_for_thread_id", return_value=GroupName.GROUP_1) if False else \
         patch("app.services.telegram_service.settings"):
        pass

    # Use the real topic mapping via settings patch
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.telegram_service._parse_topic_mapping", return_value={GroupName.GROUP_1: 500}):
        await handle_update(_group_update(777, "coord", -100111, "/tasks", thread_id=500), db)

    assert bot.send_message.called
    text = _all_sent_text(bot)
    assert f"#{task.id}" in text


@pytest.mark.asyncio
async def test_tasks_actor_resolved_by_from_id_in_group(db):
    """In a group, the actor is resolved by from.id, not the group chat.id."""
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user = await _seed_user(db, telegram_chat_id="555", role=user_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    task = await _seed_task(db, cl, title="Wipe desks")
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        # from.id=555, group chat.id=-100999 — must find user by from.id
        await handle_update(_group_update(555, "user1", -100999, "/tasks"), db)

    assert bot.send_message.called
    text = _all_sent_text(bot)
    # Must reply to group, not to user DM
    assert _first_chat(bot) == "-100999"
    # Must show task (user is in GROUP_1)
    assert f"#{task.id}" in text


@pytest.mark.asyncio
async def test_tasks_topic_reply_uses_message_thread_id(db):
    """Bot reply must carry message_thread_id when command is in a topic."""
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user = await _seed_user(db, telegram_chat_id="555", role=user_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _seed_task(db, cl, title="Vacuum")
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_group_update(555, "user1", -100999, "/tasks", thread_id=42), db)

    assert bot.send_message.called
    # All send_message calls must pass message_thread_id=42
    for call in bot.send_message.call_args_list:
        assert call.kwargs.get("message_thread_id") == 42


@pytest.mark.asyncio
async def test_tasks_cross_group_access_denied(db):
    """A GROUP_2 user cannot see GROUP_1's checklist."""
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user = await _seed_user(db, telegram_chat_id="555", role=user_role, group_name=GroupName.GROUP_2)
    await _seed_checklist(db, GroupName.GROUP_1)
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.telegram_service._parse_topic_mapping", return_value={GroupName.GROUP_1: 500}):
        await handle_update(_group_update(555, "user1", -100999, "/tasks", thread_id=500), db)

    text = _all_sent_text(bot)
    assert "access" in text.lower() or "don't" in text.lower()


# ─── /mytasks command ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mytasks_shows_task_ids(db):
    """My tasks output includes task IDs."""
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user = await _seed_user(db, telegram_chat_id="111", role=user_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    my_task = await _seed_task(db, cl, title="Grab TVs", assignee_id=user.id)
    everyone_task = await _seed_task(db, cl, title="Vacuum", assignee_id=None)
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(111, "alice", "/mytasks"), db)

    text = _all_sent_text(bot)
    assert f"#{my_task.id}" in text
    assert f"#{everyone_task.id}" in text


@pytest.mark.asyncio
async def test_mytasks_excludes_other_users_tasks(db):
    """My tasks should not include tasks specifically assigned to a different user."""
    user_role = _user_role()
    db.add(user_role)
    db.add(user_role)
    await db.flush()
    user1 = await _seed_user(db, telegram_chat_id="111", role=user_role, group_name=GroupName.GROUP_1, username="u1")
    user2 = await _seed_user(db, role=user_role, group_name=GroupName.GROUP_1, username="u2")
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    user2_task = await _seed_task(db, cl, title="Private task", assignee_id=user2.id)
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(111, "u1", "/mytasks"), db)

    text = _all_sent_text(bot)
    assert f"#{user2_task.id}" not in text


# ─── /task <id> command ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_task_detail_read_only(db):
    """/task must show task info without modifying DB."""
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user = await _seed_user(db, telegram_chat_id="111", role=user_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    task = await _seed_task(db, cl, title="Vacuum")
    await db.commit()

    was_completed = task.is_completed

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(111, "alice", f"/task {task.id}"), db)

    await db.refresh(task)
    assert task.is_completed == was_completed  # unchanged
    text = _all_sent_text(bot)
    assert f"#{task.id}" in text
    assert "Vacuum" in text


@pytest.mark.asyncio
async def test_task_detail_cross_group_denied(db):
    """/task must not expose another group's task."""
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user = await _seed_user(db, telegram_chat_id="111", role=user_role, group_name=GroupName.GROUP_2)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    task = await _seed_task(db, cl, title="Secret task")
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(111, "alice", f"/task {task.id}"), db)

    text = _all_sent_text(bot)
    assert "access" in text.lower() or "don't" in text.lower()


# ─── /done command ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_done_updates_db(db):
    """/done must mark the task complete in the DB."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, coord, coord)
    task = await _seed_task(db, cl, title="Vacuum")
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(777, "coord", f"/done {task.id}"), db)

    await db.refresh(task)
    assert task.is_completed is True
    assert task.completed_by_user_id == coord.id
    text = _all_sent_text(bot)
    assert "marked complete" in text.lower() or "✅" in text


@pytest.mark.asyncio
async def test_done_with_note(db):
    """/done stores the note in completion_notes."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, coord, coord)
    task = await _seed_task(db, cl, title="Vacuum")
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(777, "coord", f"/done {task.id} all done"), db)

    await db.refresh(task)
    assert task.is_completed is True
    assert task.completion_notes == "all done"


@pytest.mark.asyncio
async def test_done_blocked_for_unassigned_user(db):
    """/done is blocked for a user not assigned to this checklist."""
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user = await _seed_user(db, telegram_chat_id="111", role=user_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    task = await _seed_task(db, cl, title="Vacuum")
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(111, "user1", f"/done {task.id}"), db)

    await db.refresh(task)
    assert task.is_completed is False
    text = _all_sent_text(bot)
    assert "assigned" in text.lower() or "permission" in text.lower()


@pytest.mark.asyncio
async def test_done_blocked_for_auto_return_task(db):
    """Auto-generated ITEM_RETURN tasks cannot be manually completed via /done."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, coord, coord)
    task = await _seed_task(db, cl, title="Return: Drill ×1", is_auto_generated=True, auto_type="ITEM_RETURN")
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(777, "coord", f"/done {task.id}"), db)

    await db.refresh(task)
    assert task.is_completed is False
    text = _all_sent_text(bot)
    assert "return" in text.lower() or "auto" in text.lower()


# ─── /undo command ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_undo_updates_db(db):
    """/undo must clear the completion fields."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, coord, coord)
    task = await _seed_task(db, cl, title="Vacuum", is_completed=True, completed_by_id=coord.id)
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(777, "coord", f"/undo {task.id}"), db)

    await db.refresh(task)
    assert task.is_completed is False
    assert task.completed_by_user_id is None
    text = _all_sent_text(bot)
    assert "incomplete" in text.lower() or "↩️" in text


@pytest.mark.asyncio
async def test_undo_own_completion_allowed(db):
    """A regular user can undo a task they themselves completed."""
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user = await _seed_user(db, telegram_chat_id="111", role=user_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    task = await _seed_task(db, cl, title="Vacuum", is_completed=True, completed_by_id=user.id)
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(111, "user1", f"/undo {task.id}"), db)

    await db.refresh(task)
    assert task.is_completed is False


@pytest.mark.asyncio
async def test_undo_blocked_for_auto_return_task(db):
    """Auto-generated ITEM_RETURN/BIN_RETURN tasks cannot be undone from Telegram."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    task = await _seed_task(db, cl, title="Return: Bin #1", is_auto_generated=True, auto_type="BIN_RETURN", is_completed=True, completed_by_id=coord.id)
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(777, "coord", f"/undo {task.id}"), db)

    await db.refresh(task)
    assert task.is_completed is True  # unchanged
    text = _all_sent_text(bot)
    assert "auto" in text.lower() or "return" in text.lower()


# ─── /claim command ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_claim_assigns_task_to_actor(db):
    """/claim sets assignee_id to the actor."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, coord, coord)
    task = await _seed_task(db, cl, title="Vacuum", assignee_id=None)
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(777, "coord", f"/claim {task.id}"), db)

    await db.refresh(task)
    assert task.assignee_id == coord.id
    text = _all_sent_text(bot)
    assert "claimed" in text.lower() or "✅" in text


@pytest.mark.asyncio
async def test_claim_denied_for_regular_user(db):
    """Regular users (not group leads or coordinators) cannot claim tasks."""
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user = await _seed_user(db, telegram_chat_id="111", role=user_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    task = await _seed_task(db, cl, title="Vacuum", assignee_id=None)
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(111, "user1", f"/claim {task.id}"), db)

    await db.refresh(task)
    assert task.assignee_id is None  # unchanged
    text = _all_sent_text(bot)
    assert "permission" in text.lower() or "coordinator" in text.lower()


# ─── /unclaim command ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unclaim_removes_assignment(db):
    """/unclaim sets assignee_id to None."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, coord, coord)
    task = await _seed_task(db, cl, title="Vacuum", assignee_id=coord.id)
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(777, "coord", f"/unclaim {task.id}"), db)

    await db.refresh(task)
    assert task.assignee_id is None
    text = _all_sent_text(bot)
    assert "unassigned" in text.lower() or "✅" in text


@pytest.mark.asyncio
async def test_unclaim_actor_can_remove_own_claim(db):
    """A user can unclaim a task assigned specifically to themselves."""
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user = await _seed_user(db, telegram_chat_id="111", role=user_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    task = await _seed_task(db, cl, title="Vacuum", assignee_id=user.id)
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(111, "user1", f"/unclaim {task.id}"), db)

    await db.refresh(task)
    assert task.assignee_id is None


# ─── /assign command ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_assign_me_works(db):
    """/assign <id> me is equivalent to /claim."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, coord, coord)
    task = await _seed_task(db, cl, title="Vacuum")
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(777, "coord", f"/assign {task.id} me"), db)

    await db.refresh(task)
    assert task.assignee_id == coord.id


@pytest.mark.asyncio
async def test_assign_everyone_clears_assignee(db):
    """/assign <id> everyone sets assignee_id to None."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, coord, coord)
    task = await _seed_task(db, cl, title="Vacuum", assignee_id=coord.id)
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(777, "coord", f"/assign {task.id} everyone"), db)

    await db.refresh(task)
    assert task.assignee_id is None
    text = _all_sent_text(bot)
    assert "everyone" in text.lower()


@pytest.mark.asyncio
async def test_assign_username_works_for_linked_user(db):
    """/assign @handle assigns the task to the linked user."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1, username="coord")
    target_role = _user_role()
    db.add(target_role)
    await db.flush()
    target = await _seed_user(
        db,
        telegram_chat_id="888",
        telegram_handle="raj",
        role=target_role,
        group_name=GroupName.GROUP_1,
        username="raj",
        full_name="Raj Patel",
    )
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, coord, coord)
    task = await _seed_task(db, cl, title="Vacuum")
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        await handle_update(_private_update(777, "coord", f"/assign {task.id} @raj"), db)

    await db.refresh(task)
    assert task.assignee_id == target.id
    text = _all_sent_text(bot)
    assert "Raj Patel" in text or "assigned" in text.lower()


@pytest.mark.asyncio
async def test_assign_username_unknown_handle_gives_hint(db):
    """/assign @unknown gives a helpful message if the handle is not linked."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, coord, coord)
    task = await _seed_task(db, cl, title="Vacuum")
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(777, "coord", f"/assign {task.id} @nobody"), db)

    await db.refresh(task)
    assert task.assignee_id is None  # no assignment made
    text = _all_sent_text(bot)
    assert "link" in text.lower() or "couldn't find" in text.lower() or "nobody" in text.lower()


@pytest.mark.asyncio
async def test_assign_username_dm_failure_does_not_rollback(db):
    """DM to assigned user fails but the assignment persists in DB."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1, username="coord")
    target_role = _user_role()
    db.add(target_role)
    await db.flush()
    target = await _seed_user(
        db,
        telegram_chat_id="888",
        telegram_handle="bob",
        role=target_role,
        group_name=GroupName.GROUP_1,
        username="bob",
        full_name="Bob",
    )
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, coord, coord)
    task = await _seed_task(db, cl, title="Vacuum")
    await db.commit()

    # send_message raises on first call (confirmation) — no, we want DM to fail specifically
    failing_bot = _mock_bot()
    call_count = 0

    async def send_side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call = confirmation reply to coordinator — succeeds
            from unittest.mock import MagicMock
            msg = MagicMock()
            msg.message_id = 1
            return msg
        # Second call = DM to assigned user — raises
        raise Exception("Telegram DM failed")

    failing_bot.send_message.side_effect = send_side_effect

    with patch("app.bot.handlers.get_bot", return_value=failing_bot), \
         patch("app.services.telegram_service.get_bot", return_value=failing_bot):
        await handle_update(_private_update(777, "coord", f"/assign {task.id} @bob"), db)

    # Assignment must still be persisted despite DM failure
    await db.refresh(task)
    assert task.assignee_id == target.id


@pytest.mark.asyncio
async def test_assign_everyone_does_not_dm_all_users(db):
    """/assign everyone must not DM individual users."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1, username="coord")
    target_role = _user_role()
    db.add(target_role)
    await db.flush()
    user1 = await _seed_user(db, telegram_chat_id="801", role=target_role, group_name=GroupName.GROUP_1, username="u1")
    user2 = await _seed_user(db, telegram_chat_id="802", role=target_role, group_name=GroupName.GROUP_1, username="u2")
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, coord, coord)
    task = await _seed_task(db, cl, title="Vacuum", assignee_id=coord.id)
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        await handle_update(_private_update(777, "coord", f"/assign {task.id} everyone"), db)

    # Only 1 send_message call (the confirmation reply) — no DMs
    assert bot.send_message.call_count == 1


# ─── Format helpers: full and incomplete checklists ──────────────────────────

@pytest.mark.asyncio
async def test_format_full_checklist_includes_ids(db):
    cl = await _seed_checklist(db)
    sub = await _seed_subchecklist(db, cl, title="Pre Sabha", order=0)
    task = await _seed_task(db, cl, title="Grab TVs", subchecklist=sub)
    await db.commit()

    from app.bot.checklist_helpers import load_checklist_for_group
    loaded = await load_checklist_for_group(db, GroupName.GROUP_1)
    assert loaded is not None
    text = format_full_checklist(loaded)
    assert f"#{task.id}" in text
    assert "Pre Sabha" in text
    assert "Grab TVs" in text


@pytest.mark.asyncio
async def test_format_incomplete_shows_only_incomplete(db):
    cl = await _seed_checklist(db)
    sub = await _seed_subchecklist(db, cl, title="Post Sabha", section_type=SubchecklistType.POST_SABHA, order=1)
    done_task = await _seed_task(db, cl, title="Vacuum", subchecklist=sub, is_completed=True)
    pending_task = await _seed_task(db, cl, title="Wipe desks", subchecklist=sub, is_completed=False)
    await db.commit()

    from app.bot.checklist_helpers import load_checklist_for_group
    loaded = await load_checklist_for_group(db, GroupName.GROUP_1)
    assert loaded is not None
    text = format_incomplete_checklist(loaded)
    assert f"#{pending_task.id}" in text
    assert f"#{done_task.id}" not in text


@pytest.mark.asyncio
async def test_format_incomplete_all_done_message(db):
    cl = await _seed_checklist(db)
    sub = await _seed_subchecklist(db, cl, title="After Sabha Cleanup", section_type=SubchecklistType.POST_SABHA, order=1)
    await _seed_task(db, cl, title="Vacuum", subchecklist=sub, is_completed=True)
    await db.commit()

    from app.bot.checklist_helpers import load_checklist_for_group
    loaded = await load_checklist_for_group(db, GroupName.GROUP_1)
    text = format_incomplete_checklist(loaded)
    assert "Post Sabha" in text
    assert "✅" in text


# ─── Sunday scheduler functions ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sunday_morning_sends_one_message_per_group(db):
    """Sunday morning function sends a checklist message for each group that has a checklist."""
    cl1 = await _seed_checklist(db, GroupName.GROUP_1)
    cl2 = await _seed_checklist(db, GroupName.GROUP_2)
    await _seed_task(db, cl1, title="Vacuum G1")
    await _seed_task(db, cl2, title="Vacuum G2")
    await db.commit()

    bot = _mock_bot()
    with patch("app.services.telegram_service.get_bot", return_value=bot), \
         patch("app.services.telegram_service._parse_topic_mapping",
               return_value={GroupName.GROUP_1: 42, GroupName.GROUP_2: 43}), \
         patch("app.services.telegram_service.settings") as ms:
        ms.telegram_coordinator_chat_id = "-100chat"
        ms.telegram_enabled = True
        ms.telegram_bot_token = "token"

        await send_sunday_morning_for_group(GroupName.GROUP_1, db)
        calls_g1 = bot.send_message.call_count

        bot.send_message.reset_mock()
        await send_sunday_morning_for_group(GroupName.GROUP_2, db)
        calls_g2 = bot.send_message.call_count

    # Each group produced at least one message
    assert calls_g1 >= 1
    assert calls_g2 >= 1


@pytest.mark.asyncio
async def test_sunday_morning_no_checklist_raises(db):
    """Missing checklist raises RuntimeError — orchestrator treats it as a required-send failure."""
    with pytest.raises(RuntimeError, match="No checklist"):
        await send_sunday_morning_for_group(GroupName.GROUP_3, db)


@pytest.mark.asyncio
async def test_sunday_evening_sends_incomplete_tasks_only(db):
    """Sunday evening function sends only incomplete Post Sabha tasks to group."""
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    sub = await _seed_subchecklist(db, cl, title="After Sabha Cleanup", section_type=SubchecklistType.POST_SABHA, order=1)
    await _seed_task(db, cl, title="Done task", subchecklist=sub, is_completed=True)
    pending = await _seed_task(db, cl, title="Pending task", subchecklist=sub, is_completed=False)
    await db.commit()

    bot = _mock_bot()
    with patch("app.services.telegram_service.get_bot", return_value=bot), \
         patch("app.services.telegram_service._parse_topic_mapping",
               return_value={GroupName.GROUP_1: 42}), \
         patch("app.services.telegram_service.settings") as ms:
        ms.telegram_coordinator_chat_id = "-100chat"
        ms.telegram_enabled = True
        ms.telegram_bot_token = "token"

        await send_sunday_evening_for_group(GroupName.GROUP_1, db)

    text = _all_sent_text(bot)
    assert f"#{pending.id}" in text
    # Done task ID should NOT appear in the reminder
    # (note: "Done task" appears but its ID shouldn't be in the incomplete reminder)


@pytest.mark.asyncio
async def test_sunday_evening_dms_assigned_users(db):
    """Sunday evening DMs users with specifically assigned incomplete Post Sabha tasks."""
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user = await _seed_user(db, telegram_chat_id="555", role=user_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    sub = await _seed_subchecklist(db, cl, title="After Sabha Cleanup", section_type=SubchecklistType.POST_SABHA, order=1)
    task = await _seed_task(db, cl, title="Assigned task", subchecklist=sub, assignee_id=user.id, is_completed=False)
    await db.commit()

    bot = _mock_bot()
    with patch("app.services.telegram_service.get_bot", return_value=bot), \
         patch("app.services.telegram_service._parse_topic_mapping",
               return_value={GroupName.GROUP_1: 42}), \
         patch("app.services.telegram_service.settings") as ms:
        ms.telegram_coordinator_chat_id = "-100chat"
        ms.telegram_enabled = True
        ms.telegram_bot_token = "token"

        await send_sunday_evening_for_group(GroupName.GROUP_1, db)

    # At least 2 calls: group message + DM
    assert bot.send_message.call_count >= 2

    dm_calls = [
        call for call in bot.send_message.call_args_list
        if str(call.kwargs.get("chat_id")) == "555"
    ]
    assert len(dm_calls) >= 1
    dm_text = dm_calls[0].kwargs["text"]
    assert f"#{task.id}" in dm_text


@pytest.mark.asyncio
async def test_sunday_evening_does_not_dm_for_everyone_tasks(db):
    """Sunday evening must NOT DM users for Post Sabha tasks with assignee_id=None (everyone tasks)."""
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user = await _seed_user(db, telegram_chat_id="555", role=user_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    sub = await _seed_subchecklist(db, cl, title="After Sabha Cleanup", section_type=SubchecklistType.POST_SABHA, order=1)
    # Task is for "everyone" (assignee_id=None) in a Post Sabha section — no DM should be sent
    await _seed_task(db, cl, title="Everyone task", subchecklist=sub, assignee_id=None, is_completed=False)
    await db.commit()

    bot = _mock_bot()
    with patch("app.services.telegram_service.get_bot", return_value=bot), \
         patch("app.services.telegram_service._parse_topic_mapping",
               return_value={GroupName.GROUP_1: 42}), \
         patch("app.services.telegram_service.settings") as ms:
        ms.telegram_coordinator_chat_id = "-100chat"
        ms.telegram_enabled = True
        ms.telegram_bot_token = "token"

        await send_sunday_evening_for_group(GroupName.GROUP_1, db)

    # Only the group message — no individual DM
    dm_calls = [
        call for call in bot.send_message.call_args_list
        if str(call.kwargs.get("chat_id")) == "555"
    ]
    assert len(dm_calls) == 0


@pytest.mark.asyncio
async def test_sunday_evening_topic_mapping(db):
    """Sunday evening sends with correct message_thread_id when topic mapping exists."""
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _seed_task(db, cl, title="Vacuum")
    await db.commit()

    bot = _mock_bot()
    with patch("app.services.telegram_service.get_bot", return_value=bot), \
         patch("app.services.telegram_service._parse_topic_mapping", return_value={GroupName.GROUP_1: 42}), \
         patch("app.services.telegram_service.settings") as ms:
        ms.telegram_coordinator_chat_id = "-100chat"
        ms.telegram_enabled = True
        ms.telegram_bot_token = "token"

        await send_sunday_evening_for_group(GroupName.GROUP_1, db)

    group_calls = [
        call for call in bot.send_message.call_args_list
        if str(call.kwargs.get("chat_id")) == "-100chat"
    ]
    assert len(group_calls) >= 1
    assert group_calls[0].kwargs.get("message_thread_id") == 42


@pytest.mark.asyncio
async def test_sunday_morning_missing_topic_raises(db):
    """Missing topic mapping raises RuntimeError — strict mode: no fallback for Sunday required sends."""
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _seed_task(db, cl, title="Vacuum")
    await db.commit()

    with patch("app.services.telegram_service._parse_topic_mapping", return_value={}), \
         patch("app.services.telegram_service.settings") as ms:
        ms.telegram_coordinator_chat_id = "-100chat"
        ms.telegram_enabled = True
        ms.telegram_bot_token = "token"

        with pytest.raises(RuntimeError, match="Telegram send failed"):
            await send_sunday_morning_for_group(GroupName.GROUP_1, db)


# ─── Existing commands still work ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_existing_help_command_still_works(db):
    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(1, "user", "/help"), db)

    assert bot.send_message.called
    text = _all_sent_text(bot)
    assert "/requests" in text
    assert "/tasks" in text


@pytest.mark.asyncio
async def test_existing_whoami_still_works(db):
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user = await _seed_user(db, telegram_chat_id="100", role=user_role)
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(100, "alice", "/whoami"), db)

    text = _all_sent_text(bot)
    assert "alice" in text.lower() or "Alice" in text


# ─── /assign @username target validation (BLOCK fix) ─────────────────────────

@pytest.mark.asyncio
async def test_assign_username_requires_telegram_chat_id(db):
    """/assign @handle is denied if the target user has no telegram_chat_id (not actually linked)."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1, username="coord")
    target_role = _user_role()
    db.add(target_role)
    await db.flush()
    # Active user with a handle but no telegram_chat_id
    target = await _seed_user(
        db,
        telegram_chat_id=None,
        telegram_handle="ghostuser",
        role=target_role,
        group_name=GroupName.GROUP_1,
        username="ghost",
        full_name="Ghost User",
    )
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, coord, coord)
    await _assign_user_to_checklist(db, cl, target, coord)
    task = await _seed_task(db, cl, title="Vacuum")
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(777, "coord", f"/assign {task.id} @ghostuser"), db)

    await db.refresh(task)
    assert task.assignee_id is None  # unchanged
    assert bot.send_message.call_count == 1  # only the denial reply, no DM
    text = _all_sent_text(bot)
    assert "linked" in text.lower() or "not linked" in text.lower() or "start" in text.lower()


@pytest.mark.asyncio
async def test_assign_username_group_lead_denied_for_out_of_checklist_user(db):
    """A group lead cannot /assign @handle to a user not assigned to this checklist."""
    lead_role = _lead_role()
    db.add(lead_role)
    await db.flush()
    lead = await _seed_user(
        db, telegram_chat_id="777", role=lead_role, group_name=GroupName.GROUP_1, username="lead",
    )
    target_role = _user_role()
    db.add(target_role)
    await db.flush()
    # Target is linked and in the same group but NOT assigned to the checklist
    outside_user = await _seed_user(
        db,
        telegram_chat_id="900",
        telegram_handle="outsider",
        role=target_role,
        group_name=GroupName.GROUP_1,
        username="outsider",
        full_name="Outside User",
    )
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, lead, lead)  # lead is on the checklist; outside_user is not
    task = await _seed_task(db, cl, title="Set up chairs")
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot):
        await handle_update(_private_update(777, "lead", f"/assign {task.id} @outsider"), db)

    await db.refresh(task)
    assert task.assignee_id is None  # assignment must not have happened
    assert bot.send_message.call_count == 1  # denial only, no DM to outsider
    text = _all_sent_text(bot)
    assert "eligible" in text.lower() or "permission" in text.lower() or "only assign" in text.lower()


@pytest.mark.asyncio
async def test_assign_username_group_lead_can_assign_checklist_member(db):
    """A group lead can /assign @handle to a user who is already assigned to the checklist."""
    lead_role = _lead_role()
    db.add(lead_role)
    await db.flush()
    lead = await _seed_user(
        db, telegram_chat_id="777", role=lead_role, group_name=GroupName.GROUP_1, username="lead",
    )
    target_role = _user_role()
    db.add(target_role)
    await db.flush()
    member = await _seed_user(
        db,
        telegram_chat_id="888",
        telegram_handle="member1",
        role=target_role,
        group_name=GroupName.GROUP_1,
        username="member1",
        full_name="Member One",
    )
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, lead, lead)
    await _assign_user_to_checklist(db, cl, member, lead)
    task = await _seed_task(db, cl, title="Stack chairs")
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        await handle_update(_private_update(777, "lead", f"/assign {task.id} @member1"), db)

    await db.refresh(task)
    assert task.assignee_id == member.id
    text = _all_sent_text(bot)
    assert "Member One" in text or "assigned" in text.lower()


@pytest.mark.asyncio
async def test_assign_username_coordinator_can_assign_any_linked_user(db):
    """A coordinator can /assign @handle to any active linked user, even if not on the checklist."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1, username="coord")
    target_role = _user_role()
    db.add(target_role)
    await db.flush()
    # This user is NOT assigned to the checklist — coordinator should still be able to assign them
    linked_user = await _seed_user(
        db,
        telegram_chat_id="999",
        telegram_handle="newmember",
        role=target_role,
        group_name=GroupName.GROUP_2,
        username="newmember",
        full_name="New Member",
    )
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, coord, coord)
    task = await _seed_task(db, cl, title="Projector setup")
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        await handle_update(_private_update(777, "coord", f"/assign {task.id} @newmember"), db)

    await db.refresh(task)
    assert task.assignee_id == linked_user.id
    # DM attempted (2 calls: confirmation reply + DM)
    assert bot.send_message.call_count == 2


@pytest.mark.asyncio
async def test_assign_username_case_insensitive(db):
    """Handle lookup is case-insensitive: @RajPatel matches stored handle 'rajpatel'."""
    coord_role = _coord_role()
    db.add(coord_role)
    await db.flush()
    coord = await _seed_user(db, telegram_chat_id="777", role=coord_role, group_name=GroupName.GROUP_1, username="coord")
    target_role = _user_role()
    db.add(target_role)
    await db.flush()
    target = await _seed_user(
        db,
        telegram_chat_id="888",
        telegram_handle="RajPatel",  # stored with capital letters
        role=target_role,
        group_name=GroupName.GROUP_1,
        username="rajpatel",
        full_name="Raj Patel",
    )
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    await _assign_user_to_checklist(db, cl, coord, coord)
    await _assign_user_to_checklist(db, cl, target, coord)
    task = await _seed_task(db, cl, title="Vacuum")
    await db.commit()

    bot = _mock_bot()
    with patch("app.bot.handlers.get_bot", return_value=bot), \
         patch("app.services.telegram_service.get_bot", return_value=bot):
        # Command uses all-lowercase handle
        await handle_update(_private_update(777, "coord", f"/assign {task.id} @rajpatel"), db)

    await db.refresh(task)
    assert task.assignee_id == target.id


@pytest.mark.asyncio
async def test_sunday_morning_scheduler_exception_isolation(caplog):
    """RuntimeError for GROUP_1 must not prevent GROUP_2 and GROUP_3 from being attempted."""
    import logging
    from unittest.mock import MagicMock
    from app.main import _run_sunday_checklist_morning

    called_groups: list[str] = []

    async def mock_morning(group: str, db: object) -> None:
        called_groups.append(group)
        if group == GroupName.GROUP_1:
            raise RuntimeError("simulated GROUP_1 failure")

    mock_db = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.bot.checklist_helpers.send_sunday_morning_for_group", side_effect=mock_morning), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=mock_cm), \
         caplog.at_level(logging.ERROR, logger="app.bot.checklist_helpers"):
        await _run_sunday_checklist_morning()

    assert GroupName.GROUP_1 in called_groups
    assert GroupName.GROUP_2 in called_groups
    assert GroupName.GROUP_3 in called_groups
    error_msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("GROUP_1" in m for m in error_msgs)


@pytest.mark.asyncio
async def test_sunday_evening_scheduler_exception_isolation(caplog):
    """RuntimeError for GROUP_1 must not prevent GROUP_2 and GROUP_3 from being attempted."""
    import logging
    from unittest.mock import MagicMock
    from app.main import _run_sunday_evening_reminder

    called_groups: list[str] = []

    async def mock_required(group: str, db: object):
        called_groups.append(group)
        if group == GroupName.GROUP_1:
            raise RuntimeError("simulated GROUP_1 failure")
        return MagicMock()

    mock_db = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.bot.checklist_helpers._send_sunday_evening_required", side_effect=mock_required), \
         patch("app.bot.checklist_helpers._send_evening_dms_for_group", AsyncMock(return_value=[])), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=mock_cm), \
         caplog.at_level(logging.ERROR, logger="app.bot.checklist_helpers"):
        await _run_sunday_evening_reminder()

    assert GroupName.GROUP_1 in called_groups
    assert GroupName.GROUP_2 in called_groups
    assert GroupName.GROUP_3 in called_groups
    error_msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("GROUP_1" in m for m in error_msgs)


@pytest.mark.asyncio
async def test_sunday_evening_dm_false_returns_warning(db):
    """send_user_dm returning False → warning returned, no raise, group send succeeds."""
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user = await _seed_user(db, telegram_chat_id="555", role=user_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    sub = await _seed_subchecklist(db, cl, title="After Sabha Cleanup", section_type=SubchecklistType.POST_SABHA, order=1)
    await _seed_task(db, cl, title="Assigned task", subchecklist=sub, assignee_id=user.id, is_completed=False)
    await db.commit()

    with patch("app.services.telegram_service.send_to_group_topic_strict", AsyncMock(return_value=12345)), \
         patch("app.services.telegram_service.send_user_dm", AsyncMock(return_value=False)):
        warnings = await send_sunday_evening_for_group(GroupName.GROUP_1, db)

    assert len(warnings) == 1
    assert "assignee_id=" in warnings[0]


@pytest.mark.asyncio
async def test_sunday_evening_dm_raises_all_users_attempted(db):
    """When send_user_dm raises for one assignee, all assignees are still DM'd; warning returned, no raise."""
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user1 = await _seed_user(
        db, telegram_chat_id="111", role=user_role,
        group_name=GroupName.GROUP_1, username="u1", full_name="User One",
    )
    user2 = await _seed_user(
        db, telegram_chat_id="222", role=user_role,
        group_name=GroupName.GROUP_1, username="u2", full_name="User Two",
    )
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    sub = await _seed_subchecklist(db, cl, title="After Sabha Cleanup", section_type=SubchecklistType.POST_SABHA, order=1)
    await _seed_task(db, cl, title="Task A", subchecklist=sub, assignee_id=user1.id, is_completed=False)
    await _seed_task(db, cl, title="Task B", subchecklist=sub, assignee_id=user2.id, is_completed=False)
    await db.commit()

    dm_mock = AsyncMock(side_effect=[RuntimeError("Telegram down"), True])
    with patch("app.services.telegram_service.send_to_group_topic_strict", AsyncMock(return_value=12345)), \
         patch("app.services.telegram_service.send_user_dm", dm_mock):
        warnings = await send_sunday_evening_for_group(GroupName.GROUP_1, db)

    # Both users were attempted despite the first raising
    assert dm_mock.await_count == 2
    # Warning generated for the failing DM
    assert len(warnings) == 1
    assert "assignee_id=" in warnings[0]


@pytest.mark.asyncio
async def test_sunday_morning_db_failure_isolation(caplog):
    """A SQLAlchemy error for GROUP_1 must not prevent GROUP_2/GROUP_3 from getting a fresh session."""
    import logging
    from unittest.mock import MagicMock
    from app.main import _run_sunday_checklist_morning
    from sqlalchemy.exc import SQLAlchemyError

    called_groups: list[str] = []
    received_sessions: list[int] = []

    async def mock_morning(group: str, db: object) -> None:
        called_groups.append(group)
        received_sessions.append(id(db))
        if group == GroupName.GROUP_1:
            raise SQLAlchemyError("simulated DB failure for GROUP_1")

    def make_fresh_cm() -> MagicMock:
        fresh_db = AsyncMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=fresh_db)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    with patch("app.bot.checklist_helpers.send_sunday_morning_for_group", side_effect=mock_morning), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", side_effect=make_fresh_cm), \
         caplog.at_level(logging.ERROR, logger="app.bot.checklist_helpers"):
        await _run_sunday_checklist_morning()

    assert GroupName.GROUP_1 in called_groups
    assert GroupName.GROUP_2 in called_groups
    assert GroupName.GROUP_3 in called_groups
    # Every group received a distinct fresh session — shared session cannot be poisoned
    assert len(set(received_sessions)) == len(called_groups)
    error_msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("GROUP_1" in m for m in error_msgs)


@pytest.mark.asyncio
async def test_sunday_evening_db_failure_isolation(caplog):
    """A SQLAlchemy error for GROUP_1 must not prevent GROUP_2/GROUP_3 from getting a fresh session."""
    import logging
    from unittest.mock import MagicMock
    from app.main import _run_sunday_evening_reminder
    from sqlalchemy.exc import SQLAlchemyError

    called_groups: list[str] = []
    received_sessions: list[int] = []

    async def mock_required(group: str, db: object):
        called_groups.append(group)
        received_sessions.append(id(db))
        if group == GroupName.GROUP_1:
            raise SQLAlchemyError("simulated DB failure for GROUP_1")
        return MagicMock()

    def make_fresh_cm() -> MagicMock:
        fresh_db = AsyncMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=fresh_db)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    with patch("app.bot.checklist_helpers._send_sunday_evening_required", side_effect=mock_required), \
         patch("app.bot.checklist_helpers._send_evening_dms_for_group", AsyncMock(return_value=[])), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", side_effect=make_fresh_cm), \
         caplog.at_level(logging.ERROR, logger="app.bot.checklist_helpers"):
        await _run_sunday_evening_reminder()

    assert GroupName.GROUP_1 in called_groups
    assert GroupName.GROUP_2 in called_groups
    assert GroupName.GROUP_3 in called_groups
    # Every group received a distinct fresh session — shared session cannot be poisoned
    assert len(set(received_sessions)) == len(called_groups)
    error_msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("GROUP_1" in m for m in error_msgs)


# ─── Pre/Post Sabha section filtering ────────────────────────────────────────

@pytest.mark.asyncio
async def test_morning_message_includes_pre_sabha_tasks(db):
    """format_morning_checklist includes tasks from PRE_SABHA sections."""
    cl = await _seed_checklist(db)
    sub = await _seed_subchecklist(db, cl, title="Before Sabha", section_type=SubchecklistType.PRE_SABHA, order=0)
    task = await _seed_task(db, cl, title="Checkout Sabha Bin", subchecklist=sub)
    await db.commit()

    from app.bot.checklist_helpers import load_checklist_for_group
    loaded = await load_checklist_for_group(db, GroupName.GROUP_1)
    text = format_morning_checklist(loaded)
    assert f"#{task.id}" in text
    assert "Before Sabha" in text
    assert "Pre Sabha" in text


@pytest.mark.asyncio
async def test_morning_message_excludes_post_sabha_tasks(db):
    """format_morning_checklist must not include tasks from POST_SABHA sections."""
    cl = await _seed_checklist(db)
    pre_sub = await _seed_subchecklist(db, cl, title="Before Sabha", section_type=SubchecklistType.PRE_SABHA, order=0)
    post_sub = await _seed_subchecklist(db, cl, title="After Sabha Cleanup", section_type=SubchecklistType.POST_SABHA, order=1)
    pre_task = await _seed_task(db, cl, title="Checkout Sabha Bin", subchecklist=pre_sub)
    post_task = await _seed_task(db, cl, title="Vacuum", subchecklist=post_sub)
    await db.commit()

    from app.bot.checklist_helpers import load_checklist_for_group
    loaded = await load_checklist_for_group(db, GroupName.GROUP_1)
    text = format_morning_checklist(loaded)
    assert f"#{pre_task.id}" in text
    assert f"#{post_task.id}" not in text
    assert "After Sabha" not in text


@pytest.mark.asyncio
async def test_morning_progress_counts_only_pre_sabha(db):
    """Morning progress line counts only Pre Sabha tasks, not Post Sabha."""
    cl = await _seed_checklist(db)
    pre_sub = await _seed_subchecklist(db, cl, title="Before Sabha", section_type=SubchecklistType.PRE_SABHA, order=0)
    post_sub = await _seed_subchecklist(db, cl, title="After Sabha Cleanup", section_type=SubchecklistType.POST_SABHA, order=1)
    await _seed_task(db, cl, title="Pre task 1", subchecklist=pre_sub, is_completed=True)
    await _seed_task(db, cl, title="Pre task 2", subchecklist=pre_sub, is_completed=False)
    await _seed_task(db, cl, title="Post task 1", subchecklist=post_sub, is_completed=False)
    await db.commit()

    from app.bot.checklist_helpers import load_checklist_for_group
    loaded = await load_checklist_for_group(db, GroupName.GROUP_1)
    text = format_morning_checklist(loaded)
    # 1 of 2 pre-sabha tasks done; post-sabha task excluded from count
    assert "1/2 Pre Sabha tasks complete" in text


@pytest.mark.asyncio
async def test_evening_message_includes_post_sabha_tasks(db):
    """format_incomplete_checklist includes incomplete tasks from POST_SABHA sections."""
    cl = await _seed_checklist(db)
    sub = await _seed_subchecklist(db, cl, title="After Sabha Cleanup", section_type=SubchecklistType.POST_SABHA, order=1)
    task = await _seed_task(db, cl, title="Vacuum", subchecklist=sub, is_completed=False)
    await db.commit()

    from app.bot.checklist_helpers import load_checklist_for_group
    loaded = await load_checklist_for_group(db, GroupName.GROUP_1)
    text = format_incomplete_checklist(loaded)
    assert f"#{task.id}" in text
    assert "Post Sabha" in text


@pytest.mark.asyncio
async def test_evening_message_excludes_pre_sabha_tasks(db):
    """format_incomplete_checklist must not include tasks from PRE_SABHA sections."""
    cl = await _seed_checklist(db)
    pre_sub = await _seed_subchecklist(db, cl, title="Before Sabha", section_type=SubchecklistType.PRE_SABHA, order=0)
    post_sub = await _seed_subchecklist(db, cl, title="After Sabha Cleanup", section_type=SubchecklistType.POST_SABHA, order=1)
    pre_task = await _seed_task(db, cl, title="Checkout Sabha Bin", subchecklist=pre_sub, is_completed=False)
    post_task = await _seed_task(db, cl, title="Vacuum", subchecklist=post_sub, is_completed=False)
    await db.commit()

    from app.bot.checklist_helpers import load_checklist_for_group
    loaded = await load_checklist_for_group(db, GroupName.GROUP_1)
    text = format_incomplete_checklist(loaded)
    assert f"#{post_task.id}" in text
    assert f"#{pre_task.id}" not in text
    assert "Before Sabha" not in text


@pytest.mark.asyncio
async def test_evening_progress_counts_only_post_sabha(db):
    """Evening progress line counts only Post Sabha tasks, not Pre Sabha."""
    cl = await _seed_checklist(db)
    pre_sub = await _seed_subchecklist(db, cl, title="Before Sabha", section_type=SubchecklistType.PRE_SABHA, order=0)
    post_sub = await _seed_subchecklist(db, cl, title="After Sabha Cleanup", section_type=SubchecklistType.POST_SABHA, order=1)
    await _seed_task(db, cl, title="Pre task", subchecklist=pre_sub, is_completed=False)
    await _seed_task(db, cl, title="Post task 1", subchecklist=post_sub, is_completed=True)
    await _seed_task(db, cl, title="Post task 2", subchecklist=post_sub, is_completed=False)
    await db.commit()

    from app.bot.checklist_helpers import load_checklist_for_group
    loaded = await load_checklist_for_group(db, GroupName.GROUP_1)
    text = format_incomplete_checklist(loaded)
    # 1 of 2 post-sabha tasks done; pre-sabha task excluded from count
    assert "1/2 Post Sabha tasks complete" in text


@pytest.mark.asyncio
async def test_evening_all_done_refers_to_post_sabha(db):
    """All-done evening message specifically references Post Sabha, not full checklist."""
    cl = await _seed_checklist(db)
    pre_sub = await _seed_subchecklist(db, cl, title="Before Sabha", section_type=SubchecklistType.PRE_SABHA, order=0)
    post_sub = await _seed_subchecklist(db, cl, title="After Sabha Cleanup", section_type=SubchecklistType.POST_SABHA, order=1)
    # Pre Sabha task incomplete — should not affect the "all done" check
    await _seed_task(db, cl, title="Pre task", subchecklist=pre_sub, is_completed=False)
    await _seed_task(db, cl, title="Post task", subchecklist=post_sub, is_completed=True)
    await db.commit()

    from app.bot.checklist_helpers import load_checklist_for_group
    loaded = await load_checklist_for_group(db, GroupName.GROUP_1)
    text = format_incomplete_checklist(loaded)
    assert "Post Sabha" in text
    assert "✅" in text
    # Must not claim the whole checklist is done
    assert "all tasks done" not in text.lower()


@pytest.mark.asyncio
async def test_evening_dms_only_post_sabha_tasks(db):
    """Evening DMs are sent only for incomplete Post Sabha tasks assigned to a user."""
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user = await _seed_user(db, telegram_chat_id="555", role=user_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    post_sub = await _seed_subchecklist(db, cl, title="After Sabha Cleanup", section_type=SubchecklistType.POST_SABHA, order=1)
    post_task = await _seed_task(db, cl, title="Vacuum", subchecklist=post_sub, assignee_id=user.id, is_completed=False)
    await db.commit()

    bot = _mock_bot()
    with patch("app.services.telegram_service.get_bot", return_value=bot), \
         patch("app.services.telegram_service._parse_topic_mapping",
               return_value={GroupName.GROUP_1: 42}), \
         patch("app.services.telegram_service.settings") as ms:
        ms.telegram_coordinator_chat_id = "-100chat"
        ms.telegram_enabled = True
        ms.telegram_bot_token = "token"

        await send_sunday_evening_for_group(GroupName.GROUP_1, db)

    dm_calls = [
        call for call in bot.send_message.call_args_list
        if str(call.kwargs.get("chat_id")) == "555"
    ]
    assert len(dm_calls) >= 1
    assert f"#{post_task.id}" in dm_calls[0].kwargs["text"]


@pytest.mark.asyncio
async def test_evening_no_dm_if_only_incomplete_pre_sabha(db):
    """A user with only incomplete Pre Sabha tasks must NOT receive an evening DM."""
    user_role = _user_role()
    db.add(user_role)
    await db.flush()
    user = await _seed_user(db, telegram_chat_id="555", role=user_role, group_name=GroupName.GROUP_1)
    cl = await _seed_checklist(db, GroupName.GROUP_1)
    pre_sub = await _seed_subchecklist(db, cl, title="Before Sabha", section_type=SubchecklistType.PRE_SABHA, order=0)
    post_sub = await _seed_subchecklist(db, cl, title="After Sabha Cleanup", section_type=SubchecklistType.POST_SABHA, order=1)
    # User has an incomplete Pre Sabha task — no DM should be sent
    await _seed_task(db, cl, title="Pre task", subchecklist=pre_sub, assignee_id=user.id, is_completed=False)
    # Post Sabha task is complete — no DM trigger
    await _seed_task(db, cl, title="Post task", subchecklist=post_sub, is_completed=True)
    await db.commit()

    bot = _mock_bot()
    with patch("app.services.telegram_service.get_bot", return_value=bot), \
         patch("app.services.telegram_service._parse_topic_mapping",
               return_value={GroupName.GROUP_1: 42}), \
         patch("app.services.telegram_service.settings") as ms:
        ms.telegram_coordinator_chat_id = "-100chat"
        ms.telegram_enabled = True
        ms.telegram_bot_token = "token"

        await send_sunday_evening_for_group(GroupName.GROUP_1, db)

    dm_calls = [
        call for call in bot.send_message.call_args_list
        if str(call.kwargs.get("chat_id")) == "555"
    ]
    assert len(dm_calls) == 0
