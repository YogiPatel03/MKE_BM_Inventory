"""
Telegram checklist formatting, query helpers, and Sunday scheduler logic.

All formatting functions are pure (no DB) — they require relationships to be
eagerly loaded by the caller. All query functions are read-only; they never
auto-create checklists.
"""
import asyncio
import html
import logging
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal
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
    Raises RuntimeError if no checklist exists — required send; orchestrator marks group failed.
    """
    from app.services.telegram_service import send_to_group_topic_strict

    checklist = await load_checklist_for_group(db, group_name)
    if not checklist:
        raise RuntimeError(f"No checklist for group {group_name}")

    text = format_full_checklist(checklist)
    for chunk in split_messages(text):
        result = await send_to_group_topic_strict(group_name, chunk)
        if result is None:
            raise RuntimeError(f"Telegram send failed for group {group_name}")
    log.info("Sunday morning: sent checklist for group %s", group_name)


_DM_TIMEOUT = 15.0       # per-DM send timeout (seconds)
_DM_PHASE_TIMEOUT = 60.0  # total DM phase timeout per group (seconds)


async def _send_sunday_evening_required(group_name: str, db: AsyncSession) -> "Checklist":
    """
    Load the checklist and send the incomplete-task reminder to the group topic.
    Raises RuntimeError on failure so the orchestrator marks the group as failed
    and retryable. Returns the loaded checklist for use in the DM phase.
    """
    from app.services.telegram_service import send_to_group_topic_strict

    checklist = await load_checklist_for_group(db, group_name)
    if not checklist:
        raise RuntimeError(f"No checklist for group {group_name}")

    text = format_incomplete_checklist(checklist)
    for chunk in split_messages(text):
        result = await send_to_group_topic_strict(group_name, chunk)
        if result is None:
            raise RuntimeError(f"Telegram send failed for group {group_name}")
    log.info("Sunday evening: sent reminder for group %s", group_name)
    return checklist


async def _send_evening_dms_for_group(
    group_name: str, checklist: "Checklist", db: AsyncSession
) -> list[str]:
    """
    Send DMs to users with assigned incomplete tasks. Best-effort only — all
    failures are returned as warning strings and never raise. Applies a per-DM
    timeout so a single slow send cannot stall the phase.
    """
    from app.models.user import User
    from app.services.telegram_service import send_user_dm

    assignee_tasks: dict[int, list[ChecklistItem]] = {}
    for task in checklist.items:
        if not task.is_completed and task.assignee_id is not None:
            assignee_tasks.setdefault(task.assignee_id, []).append(task)

    if not assignee_tasks:
        return []

    group_display = GroupName.DISPLAY.get(group_name, group_name)
    dm_warnings: list[str] = []

    for assignee_id, tasks in assignee_tasks.items():
        try:
            user_result = await db.execute(
                select(User).where(User.id == assignee_id, User.is_active == True)
            )
            assignee = user_result.scalar_one_or_none()
            if not assignee:
                warn = f"assignee_id={assignee_id} not found or inactive"
                log.warning("Sunday evening: %s group=%s", warn, group_name)
                dm_warnings.append(warn)
                continue
            if not assignee.telegram_chat_id:
                warn = f"assignee_id={assignee_id} has no telegram_chat_id"
                log.warning("Sunday evening: %s group=%s", warn, group_name)
                dm_warnings.append(warn)
                continue

            task_lines = "\n".join(f"• #{t.id} {html.escape(t.title)}" for t in tasks)
            dm_text = (
                f"⏰ <b>Sunday reminder — {html.escape(group_display)}</b>\n"
                f"You have {len(tasks)} incomplete task(s) assigned to you:\n"
                f"{task_lines}\n\n"
                f"Use /task &lt;id&gt; to view or /done &lt;id&gt; to mark complete."
            )
            try:
                ok = await asyncio.wait_for(send_user_dm(assignee, dm_text), timeout=_DM_TIMEOUT)
            except asyncio.TimeoutError:
                warn = f"DM timed out for assignee_id={assignee_id}"
                log.warning("Sunday evening: %s group=%s", warn, group_name)
                dm_warnings.append(warn)
                continue
            if not ok:
                warn = f"DM failed for assignee_id={assignee_id}"
                log.warning("Sunday evening: %s group=%s", warn, group_name)
                dm_warnings.append(warn)
        except Exception as exc:
            warn = f"DM error for assignee_id={assignee_id}"
            log.warning("Sunday evening: %s group=%s: %s", warn, group_name, type(exc).__name__)
            dm_warnings.append(warn)

    return dm_warnings


async def send_sunday_evening_for_group(group_name: str, db: AsyncSession) -> list[str]:
    """
    Send incomplete task reminder to a group's coordinator topic, then DM each
    linked user who has specifically assigned (non-everyone) incomplete tasks.
    Called per-group by the Sunday evening scheduler job.

    Required: group/topic send — raises on failure (including missing checklist) so the
    orchestrator marks the group as failed and retryable.
    Best-effort: individual assigned-user DMs — failures are collected as warning
    strings and returned; they never cause the group to fail.
    """
    checklist = await _send_sunday_evening_required(group_name, db)
    return await _send_evening_dms_for_group(group_name, checklist, db)


# ─── Dedup helpers (shared by APScheduler and HTTP endpoint) ──────────────────
#
# Dedup is per-job+group so that a failed group does not block its own retry:
# each group is marked only after its send succeeds. A retry within the window
# skips groups that already succeeded and retries groups that previously failed.
# Morning and evening keys are separated by the job name prefix.
#
# Concurrent duplicate prevention: per-group asyncio.Lock serializes concurrent
# callers (APScheduler + GHA HTTP trigger in the same Render process). The dedup
# check is re-evaluated inside the lock so a second waiter sees the first
# caller's mark before proceeding.
#
# Residual duplicate risk: if the Render dyno restarts while a send is in flight
# the in-memory dict is cleared and a subsequent retry may send again.
# This is accepted; a DB-backed log would eliminate it.

_DEDUP: dict[str, datetime] = {}
_DEDUP_LOCKS: dict[str, asyncio.Lock] = {}
_DEDUP_WINDOW = timedelta(minutes=30)


def _get_dedup_lock(key: str) -> asyncio.Lock:
    if key not in _DEDUP_LOCKS:
        _DEDUP_LOCKS[key] = asyncio.Lock()
    return _DEDUP_LOCKS[key]


def _group_dedup_key(job: str, group: str) -> str:
    return f"{job}:{group}:{datetime.now(_CHECKLIST_TZ).date().isoformat()}"


def _group_already_ran(job: str, group: str) -> bool:
    last = _DEDUP.get(_group_dedup_key(job, group))
    return last is not None and (datetime.now(_CHECKLIST_TZ) - last) < _DEDUP_WINDOW


def _mark_group_ran(job: str, group: str) -> None:
    _DEDUP[_group_dedup_key(job, group)] = datetime.now(_CHECKLIST_TZ)


# ─── Shared orchestrators (APScheduler + HTTP endpoint both call these) ────────

async def run_sunday_morning_all_groups() -> dict[str, str]:
    """
    Send the full weekly checklist to every group. Called by both the APScheduler
    job and the /api/internal/jobs/sunday-checklist-morning HTTP endpoint.
    Per-group dedup prevents double-sends within a 30-minute window. Succeeded
    groups are skipped on retry; failed groups are retried.
    """
    job = "sunday_morning"
    log.info("sunday morning: starting for all groups")
    results: dict[str, str] = {}
    for group in GroupName.ALL:
        key = _group_dedup_key(job, group)
        lock = _get_dedup_lock(key)
        async with lock:
            if _group_already_ran(job, group):
                log.info("sunday morning: group %s already ran within %s — skipping", group, _DEDUP_WINDOW)
                results[group] = "skipped"
                continue
            try:
                async with AsyncSessionLocal() as db:
                    await send_sunday_morning_for_group(group, db)
                _mark_group_ran(job, group)
                results[group] = "ok"
                log.info("sunday morning: group %s sent", group)
            except Exception:
                log.exception("sunday morning: group %s failed", group)
                results[group] = "error"
    return results


async def run_sunday_evening_all_groups() -> tuple[dict[str, str], dict[str, list[str]]]:
    """
    Send incomplete-task reminders to every group + DM assigned users.
    Called by both the APScheduler job and the /api/internal/jobs/sunday-checklist-evening
    HTTP endpoint. Per-group dedup prevents double-sends within a 30-minute window.
    Succeeded groups are skipped on retry; failed groups (required send failed) are retried.

    Two-phase execution:
      Phase 1 (inside per-group lock): required topic send only. Dedup is marked
        immediately after the required send succeeds, before releasing the lock and
        before DMs run. A timeout during DMs cannot cause the topic message to be
        resent on retry.
      Phase 2 (after all locks): best-effort DMs per group. Timeouts and errors
        are reported as warnings; they never make a group retryable.

    Returns (results, dm_warnings):
      results:     per-group status — "ok", "error", or "skipped"
      dm_warnings: per-group list of best-effort DM warning strings (empty groups omitted)
    """
    job = "sunday_evening"
    log.info("sunday evening: starting for all groups")
    results: dict[str, str] = {}
    dm_warnings: dict[str, list[str]] = {}
    dm_pending: list[tuple[str, "Checklist"]] = []

    for group in GroupName.ALL:
        key = _group_dedup_key(job, group)
        lock = _get_dedup_lock(key)
        async with lock:
            if _group_already_ran(job, group):
                log.info("sunday evening: group %s already ran within %s — skipping", group, _DEDUP_WINDOW)
                results[group] = "skipped"
                continue
            try:
                async with AsyncSessionLocal() as db:
                    checklist = await _send_sunday_evening_required(group, db)
                # Dedup marked before DMs: a DM timeout cannot cause the topic to resend.
                _mark_group_ran(job, group)
                results[group] = "ok"
                dm_pending.append((group, checklist))
                log.info("sunday evening: group %s required send done", group)
            except Exception:
                log.exception("sunday evening: group %s failed", group)
                results[group] = "error"

    for group, checklist in dm_pending:
        try:
            async with AsyncSessionLocal() as db:
                warnings = await asyncio.wait_for(
                    _send_evening_dms_for_group(group, checklist, db),
                    timeout=_DM_PHASE_TIMEOUT,
                )
        except asyncio.TimeoutError:
            warnings = [f"DM phase timed out for group {group}"]
            log.warning("sunday evening: DM phase timed out for group %s", group)
        except Exception as exc:
            warnings = [f"DM phase error: {type(exc).__name__}"]
            log.warning("sunday evening: DM phase error for group %s: %s", group, type(exc).__name__)
        if warnings:
            dm_warnings[group] = warnings

    return results, dm_warnings
