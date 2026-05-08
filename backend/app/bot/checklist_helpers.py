"""
Telegram checklist formatting, query helpers, and Sunday scheduler logic.

All formatting functions are pure (no DB) — they require relationships to be
eagerly loaded by the caller. All query functions are read-only; they never
auto-create checklists.
"""
import html
import logging
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.checklist import Checklist, ChecklistItem, GroupName, Subchecklist

if TYPE_CHECKING:
    from app.models.user import User

log = logging.getLogger(__name__)

_CHECKLIST_TZ = ZoneInfo("America/Chicago")
_MAX_MSG = 4000  # Telegram limit is 4096; leave headroom for HTML tags


# ─── Date helpers ─────────────────────────────────────────────────────────────

def _current_week_monday() -> date:
    today = datetime.now(_CHECKLIST_TZ).date()
    return today - timedelta(days=today.weekday())


# ─── Formatting helpers ───────────────────────────────────────────────────────

def format_task_line(task: ChecklistItem) -> str:
    """
    Format one task line for Telegram output.
    Requires task.assignee and task.completed_by to be loaded.
    """
    status = "✅" if task.is_completed else "⬜"
    title = html.escape(task.title[:80])

    if task.is_completed:
        done_by = html.escape(task.completed_by.full_name) if task.completed_by else "unknown"
        suffix = f"done by {done_by}"
    elif task.assignee_id is not None:
        name = html.escape(task.assignee.full_name) if task.assignee else "unknown"
        suffix = f"assigned: {name}"
    else:
        suffix = "everyone"

    return f"{status} #{task.id} {title} — {suffix}"


def split_messages(text: str) -> list[str]:
    """Split text into Telegram-safe chunks at newline boundaries."""
    if len(text) <= _MAX_MSG:
        return [text]

    parts: list[str] = []
    lines = text.split("\n")
    current: list[str] = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1  # +1 for the joining newline
        if current_len + line_len > _MAX_MSG and current:
            parts.append("\n".join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len

    if current:
        parts.append("\n".join(current))

    return parts


def format_full_checklist(checklist: Checklist) -> str:
    """
    Format a full checklist (all tasks by section) for Telegram.
    Requires subchecklists, items, assignee, and completed_by loaded.
    """
    group_display = GroupName.DISPLAY.get(checklist.group_name, checklist.group_name)
    week = checklist.week_start.strftime("%b %d")
    lines = [f"<b>📋 {html.escape(group_display)} — Week of {week}</b>"]

    seen_ids: set[int] = set()

    for sub in sorted(checklist.subchecklists, key=lambda s: s.section_order):
        section_items = sorted(sub.items, key=lambda t: t.item_order)
        if section_items:
            lines.append(f"\n<b>{html.escape(sub.title)}:</b>")
            for task in section_items:
                lines.append(f"  {format_task_line(task)}")
                seen_ids.add(task.id)

    unsectioned = [
        t for t in sorted(checklist.items, key=lambda t: t.item_order)
        if t.id not in seen_ids
    ]
    if unsectioned:
        lines.append("\n<b>Other:</b>")
        for task in unsectioned:
            lines.append(f"  {format_task_line(task)}")

    total = len(checklist.items)
    done = sum(1 for t in checklist.items if t.is_completed)
    lines.append(f"\n<i>{done}/{total} tasks complete</i>")
    return "\n".join(lines)


def format_incomplete_checklist(checklist: Checklist) -> str:
    """
    Format only incomplete tasks for the Sunday evening reminder.
    Requires subchecklists, items, assignee, and completed_by loaded.
    Returns a short "all done" message if nothing is incomplete.
    """
    group_display = GroupName.DISPLAY.get(checklist.group_name, checklist.group_name)
    week = checklist.week_start.strftime("%b %d")

    seen_ids: set[int] = set()
    incomplete_by_sub: dict[int, list[ChecklistItem]] = {}

    for sub in checklist.subchecklists:
        for task in sub.items:
            seen_ids.add(task.id)
            if not task.is_completed:
                incomplete_by_sub.setdefault(sub.id, []).append(task)

    unsectioned_incomplete = [
        t for t in checklist.items
        if t.id not in seen_ids and not t.is_completed
    ]

    if not any(incomplete_by_sub.values()) and not unsectioned_incomplete:
        return f"✅ <b>{html.escape(group_display)}</b> — all tasks done! Great work."

    lines = [f"<b>⏰ {html.escape(group_display)} — Incomplete tasks (week of {week}):</b>"]

    for sub in sorted(checklist.subchecklists, key=lambda s: s.section_order):
        items = incomplete_by_sub.get(sub.id, [])
        if items:
            lines.append(f"\n<b>{html.escape(sub.title)}:</b>")
            for task in sorted(items, key=lambda t: t.item_order):
                lines.append(f"  {format_task_line(task)}")

    if unsectioned_incomplete:
        lines.append("\n<b>Other:</b>")
        for task in sorted(unsectioned_incomplete, key=lambda t: t.item_order):
            lines.append(f"  {format_task_line(task)}")

    return "\n".join(lines)


# ─── Permission helpers (mirror app/routers/checklists.py) ────────────────────

def can_view_checklist(user: "User", checklist: Checklist) -> bool:
    """True if user is allowed to see this checklist. Requires checklist.assignments loaded."""
    if user.role.can_manage_users or user.role.can_manage_inventory:
        return True
    if any(a.user_id == user.id for a in checklist.assignments):
        return True
    if checklist.group_name == user.group_name:
        return True
    return False


def can_complete_on(user: "User", checklist: Checklist) -> bool:
    """True if user may mark tasks complete on this checklist. Requires checklist.assignments loaded."""
    if user.role.can_manage_users or user.role.can_manage_inventory:
        return True
    if any(a.user_id == user.id for a in checklist.assignments):
        return True
    return False


def can_manage_tasks_on(user: "User", checklist: Checklist) -> bool:
    """
    True if user may add/edit/assign tasks on this checklist.
    Mirrors _can_manage_tasks_on from app/routers/checklists.py.
    Requires checklist.assignments loaded.
    """
    if user.role.can_manage_users or user.role.can_manage_inventory:
        return True
    if (
        user.role.can_approve_requests
        and any(a.user_id == user.id for a in checklist.assignments)
        and user.group_name == checklist.group_name
    ):
        return True
    return False


# ─── DB query helpers ─────────────────────────────────────────────────────────

async def load_checklist_for_group(db: AsyncSession, group_name: str) -> Optional[Checklist]:
    """
    Read-only load of the current week's checklist for a group with all
    relationships needed for formatting and permission checks.
    Returns None without creating if no checklist exists yet.
    """
    monday = _current_week_monday()
    result = await db.execute(
        select(Checklist)
        .where(Checklist.group_name == group_name, Checklist.week_start == monday)
        .options(
            selectinload(Checklist.assignments),
            selectinload(Checklist.subchecklists)
            .selectinload(Subchecklist.items)
            .selectinload(ChecklistItem.assignee),
            selectinload(Checklist.subchecklists)
            .selectinload(Subchecklist.items)
            .selectinload(ChecklistItem.completed_by),
            selectinload(Checklist.items).selectinload(ChecklistItem.assignee),
            selectinload(Checklist.items).selectinload(ChecklistItem.completed_by),
        )
    )
    return result.scalar_one_or_none()


# ─── Sunday scheduler logic ───────────────────────────────────────────────────

async def send_sunday_morning_for_group(group_name: str, db: AsyncSession) -> None:
    """
    Send the full weekly checklist to a group's coordinator topic.
    Called per-group by the Sunday morning scheduler job.
    Skips (with a warning) if no checklist exists for the current week.
    """
    from app.services.telegram_service import send_to_group_topic

    checklist = await load_checklist_for_group(db, group_name)
    if not checklist:
        log.warning("Sunday morning: no checklist for group %s — skipping", group_name)
        return

    text = format_full_checklist(checklist)
    for chunk in split_messages(text):
        await send_to_group_topic(group_name, chunk)
    log.info("Sunday morning: sent checklist for group %s", group_name)


async def send_sunday_evening_for_group(group_name: str, db: AsyncSession) -> None:
    """
    Send incomplete task reminder to a group's coordinator topic, then DM each
    linked user who has specifically assigned (non-everyone) incomplete tasks.
    Called per-group by the Sunday evening scheduler job.
    DM failures are logged but do not affect the group message or other DMs.
    """
    from app.models.user import User
    from app.services.telegram_service import send_to_group_topic, send_user_dm

    checklist = await load_checklist_for_group(db, group_name)
    if not checklist:
        log.warning("Sunday evening: no checklist for group %s — skipping", group_name)
        return

    # Group/topic reminder
    text = format_incomplete_checklist(checklist)
    for chunk in split_messages(text):
        await send_to_group_topic(group_name, chunk)
    log.info("Sunday evening: sent reminder for group %s", group_name)

    # DM users with specifically-assigned incomplete tasks (exclude everyone tasks)
    assignee_tasks: dict[int, list[ChecklistItem]] = {}
    for task in checklist.items:
        if not task.is_completed and task.assignee_id is not None:
            assignee_tasks.setdefault(task.assignee_id, []).append(task)

    if not assignee_tasks:
        return

    group_display = GroupName.DISPLAY.get(group_name, group_name)

    for assignee_id, tasks in assignee_tasks.items():
        try:
            user_result = await db.execute(
                select(User).where(User.id == assignee_id, User.is_active == True)
            )
            assignee = user_result.scalar_one_or_none()
            if not assignee or not assignee.telegram_chat_id:
                continue

            task_lines = "\n".join(f"• #{t.id} {html.escape(t.title)}" for t in tasks)
            dm_text = (
                f"⏰ <b>Sunday reminder — {html.escape(group_display)}</b>\n"
                f"You have {len(tasks)} incomplete task(s) assigned to you:\n"
                f"{task_lines}\n\n"
                f"Use /task &lt;id&gt; to view or /done &lt;id&gt; to mark complete."
            )
            await send_user_dm(assignee, dm_text)
        except Exception:
            log.warning("Sunday evening: failed to DM assignee_id=%d for group %s", assignee_id, group_name)
