"""
Checklist service — weekly checklist generation and management.

Checklists are auto-generated every Monday for each of the 4 groups.
Each weekly checklist has two mandatory subchecklists: Pre Sabha and Post Sabha.
Return tasks are auto-created in the Post Sabha subchecklist when items/bins are
checked out, and auto-completed when they are returned.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bin_transaction import BinTransaction
from app.models.checklist import (
    Checklist,
    ChecklistAssignment,
    ChecklistItem,
    GroupName,
    Subchecklist,
    SubchecklistType,
)
from app.models.item import Item
from app.models.transaction import Transaction
from app.models.user import User

log = logging.getLogger(__name__)

# Default tasks for mandatory subchecklists
PRE_SABHA_DEFAULT_TASKS = [
    {"title": "Checkout Sabha Bin", "description": "Check out the Sabha bin before Sabha starts."},
    {"title": "Grab TVs", "description": "Set up TVs as needed for this week's Sabha."},
    {"title": "Checkout any other materials you need for this week", "description": None},
]

POST_SABHA_DEFAULT_TASKS = [
    {"title": "Vacuum", "description": "Vacuum the room after Sabha."},
    {"title": "Turn off lights", "description": "Ensure all lights are off before leaving."},
    {"title": "Empty trash cans", "description": "Empty all trash cans in the space."},
    {"title": "Wipe lap desks", "description": "Wipe down all lap desks."},
    {"title": "Leave door open", "description": "Leave the door open when done."},
]


_CHECKLIST_TZ = ZoneInfo("America/Chicago")


def _current_week_monday() -> date:
    """Return the Monday of the current week in America/Chicago time."""
    today = datetime.now(_CHECKLIST_TZ).date()
    return today - timedelta(days=today.weekday())


async def _ensure_mandatory_subchecklists(db: AsyncSession, checklist: Checklist) -> dict[str, Subchecklist]:
    """
    Ensure PRE_SABHA and POST_SABHA subchecklists exist for a checklist.
    Creates them with default tasks if missing.
    Returns dict mapping section_type → Subchecklist.
    """
    result = await db.execute(
        select(Subchecklist)
        .where(Subchecklist.checklist_id == checklist.id)
        .options(selectinload(Subchecklist.items))
    )
    existing = {s.section_type: s for s in result.scalars().all()}

    subs = {}

    # Pre Sabha
    if SubchecklistType.PRE_SABHA not in existing:
        pre = Subchecklist(
            checklist_id=checklist.id,
            title="Pre Sabha",
            section_type=SubchecklistType.PRE_SABHA,
            is_mandatory=True,
            section_order=0,
        )
        db.add(pre)
        await db.flush()

        for i, task in enumerate(PRE_SABHA_DEFAULT_TASKS):
            item = ChecklistItem(
                checklist_id=checklist.id,
                subchecklist_id=pre.id,
                title=task["title"],
                description=task["description"],
                item_order=i,
                is_auto_generated=False,
            )
            db.add(item)

        subs[SubchecklistType.PRE_SABHA] = pre
        log.info("Created Pre Sabha subchecklist for checklist=%d", checklist.id)
    else:
        subs[SubchecklistType.PRE_SABHA] = existing[SubchecklistType.PRE_SABHA]

    # Post Sabha
    if SubchecklistType.POST_SABHA not in existing:
        post = Subchecklist(
            checklist_id=checklist.id,
            title="Post Sabha",
            section_type=SubchecklistType.POST_SABHA,
            is_mandatory=True,
            section_order=1,
        )
        db.add(post)
        await db.flush()

        for i, task in enumerate(POST_SABHA_DEFAULT_TASKS):
            item = ChecklistItem(
                checklist_id=checklist.id,
                subchecklist_id=post.id,
                title=task["title"],
                description=task["description"],
                item_order=i,
                is_auto_generated=False,
            )
            db.add(item)

        subs[SubchecklistType.POST_SABHA] = post
        log.info("Created Post Sabha subchecklist for checklist=%d", checklist.id)
    else:
        subs[SubchecklistType.POST_SABHA] = existing[SubchecklistType.POST_SABHA]

    await db.flush()
    return subs


async def get_or_create_weekly_checklists(db: AsyncSession) -> list[Checklist]:
    """
    Ensure one checklist exists for each group for the current week,
    with mandatory Pre Sabha and Post Sabha subchecklists.
    Called on Monday morning by the scheduler and lazily on first access.
    """
    monday = _current_week_monday()
    created = []

    for group in GroupName.ALL:
        result = await db.execute(
            select(Checklist).where(
                Checklist.group_name == group,
                Checklist.week_start == monday,
            )
        )
        checklist = result.scalar_one_or_none()
        if not checklist:
            checklist = Checklist(group_name=group, week_start=monday, is_active=True)
            db.add(checklist)
            await db.flush()
            log.info("Auto-generated checklist: group=%s week=%s id=%d", group, monday, checklist.id)

        # Ensure mandatory subchecklists exist
        await _ensure_mandatory_subchecklists(db, checklist)
        created.append(checklist)

    return created


async def get_current_checklist_for_group(
    db: AsyncSession, group_name: str
) -> Optional[Checklist]:
    """Get (or create) the current week's checklist for a specific group."""
    monday = _current_week_monday()
    result = await db.execute(
        select(Checklist)
        .where(Checklist.group_name == group_name, Checklist.week_start == monday)
        .options(
            selectinload(Checklist.items),
            selectinload(Checklist.assignments).selectinload(ChecklistAssignment.user),
        )
    )
    checklist = result.scalar_one_or_none()
    if not checklist:
        checklist = Checklist(group_name=group_name, week_start=monday, is_active=True)
        db.add(checklist)
        await db.flush()

    # Ensure mandatory subchecklists
    await _ensure_mandatory_subchecklists(db, checklist)
    return checklist


async def _get_post_sabha_subchecklist(
    db: AsyncSession, checklist: Checklist
) -> Optional[Subchecklist]:
    """Get the Post Sabha subchecklist for a checklist, creating if needed."""
    result = await db.execute(
        select(Subchecklist).where(
            Subchecklist.checklist_id == checklist.id,
            Subchecklist.section_type == SubchecklistType.POST_SABHA,
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        subs = await _ensure_mandatory_subchecklists(db, checklist)
        sub = subs.get(SubchecklistType.POST_SABHA)
    return sub


async def add_return_task_for_transaction(
    db: AsyncSession,
    transaction: Transaction,
    user: User,
) -> Optional[ChecklistItem]:
    """
    When a non-consumable item is checked out, add a return task to the
    Post Sabha subchecklist of the borrower's group's current-week checklist.
    Returns the created ChecklistItem, or None if user has no group.
    """
    if not user.group_name:
        return None

    checklist = await get_current_checklist_for_group(db, user.group_name)
    if not checklist:
        return None

    post_sabha = await _get_post_sabha_subchecklist(db, checklist)

    item_result = await db.execute(select(Item).where(Item.id == transaction.item_id))
    item = item_result.scalar_one_or_none()
    item_name = item.name if item else f"Item #{transaction.item_id}"

    # Count existing items in Post Sabha to set order
    count_result = await db.execute(
        select(ChecklistItem).where(
            ChecklistItem.subchecklist_id == (post_sabha.id if post_sabha else None),
            ChecklistItem.checklist_id == checklist.id,
        )
    )
    existing_count = len(list(count_result.scalars().all()))

    qty_display = (
        f"{transaction.quantity:g}" if isinstance(transaction.quantity, float)
        else str(transaction.quantity)
    )

    task = ChecklistItem(
        checklist_id=checklist.id,
        subchecklist_id=post_sabha.id if post_sabha else None,
        title=f"Return: {item_name} (×{qty_display})",
        description=f"Return '{item_name}' checked out by {user.full_name}",
        item_order=existing_count,
        is_auto_generated=True,
        auto_type="ITEM_RETURN",
        linked_transaction_id=transaction.id,
    )
    db.add(task)
    await db.flush()
    log.info(
        "Auto-created return task: checklist=%d txn=%d item=%s subchecklist=%s",
        checklist.id, transaction.id, item_name,
        post_sabha.id if post_sabha else "none",
    )
    return task


async def add_return_task_for_bin_transaction(
    db: AsyncSession,
    bin_transaction: BinTransaction,
    user: User,
) -> Optional[ChecklistItem]:
    """
    When a bin is checked out, add a return task to the Post Sabha subchecklist
    of the borrower's group's current-week checklist.
    """
    if not user.group_name:
        return None

    checklist = await get_current_checklist_for_group(db, user.group_name)
    if not checklist:
        return None

    post_sabha = await _get_post_sabha_subchecklist(db, checklist)

    from app.models.bin import Bin
    bin_result = await db.execute(select(Bin).where(Bin.id == bin_transaction.bin_id))
    bin_obj = bin_result.scalar_one_or_none()
    bin_label = bin_obj.label if bin_obj else f"Bin #{bin_transaction.bin_id}"

    count_result = await db.execute(
        select(ChecklistItem).where(
            ChecklistItem.subchecklist_id == (post_sabha.id if post_sabha else None),
            ChecklistItem.checklist_id == checklist.id,
        )
    )
    existing_count = len(list(count_result.scalars().all()))

    task = ChecklistItem(
        checklist_id=checklist.id,
        subchecklist_id=post_sabha.id if post_sabha else None,
        title=f"Return Bin: {bin_label}",
        description=f"Return bin '{bin_label}' checked out by {user.full_name}",
        item_order=existing_count,
        is_auto_generated=True,
        auto_type="BIN_RETURN",
        linked_bin_transaction_id=bin_transaction.id,
    )
    db.add(task)
    await db.flush()
    log.info(
        "Auto-created bin return task: checklist=%d bin_txn=%d subchecklist=%s",
        checklist.id, bin_transaction.id,
        post_sabha.id if post_sabha else "none",
    )
    return task


async def auto_complete_return_task_for_transaction(
    db: AsyncSession,
    transaction_id: int,
    returned_by_user_id: int,
) -> Optional[ChecklistItem]:
    """
    When an item transaction is returned, find and mark the corresponding
    auto-generated return task as completed.
    """
    result = await db.execute(
        select(ChecklistItem).where(
            ChecklistItem.linked_transaction_id == transaction_id,
            ChecklistItem.is_auto_generated == True,
            ChecklistItem.is_completed == False,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        return None

    now = datetime.now(timezone.utc)
    task.is_completed = True
    task.completed_at = now
    task.completed_by_user_id = returned_by_user_id
    task.completion_notes = (task.completion_notes or "") + " [Auto-completed on return]"

    log.info("Auto-completed return task: item=%d task=%d", task.id, transaction_id)
    return task


async def auto_complete_return_task_for_bin(
    db: AsyncSession,
    bin_transaction_id: int,
    returned_by_user_id: int,
) -> Optional[ChecklistItem]:
    """
    When a bin transaction is returned, find and mark the corresponding
    auto-generated return task as completed.
    """
    result = await db.execute(
        select(ChecklistItem).where(
            ChecklistItem.linked_bin_transaction_id == bin_transaction_id,
            ChecklistItem.is_auto_generated == True,
            ChecklistItem.is_completed == False,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        return None

    now = datetime.now(timezone.utc)
    task.is_completed = True
    task.completed_at = now
    task.completed_by_user_id = returned_by_user_id
    task.completion_notes = (task.completion_notes or "") + " [Auto-completed on return]"

    log.info("Auto-completed bin return task: bin_txn=%d task=%d", bin_transaction_id, task.id)
    return task


async def complete_checklist_item(
    db: AsyncSession,
    item_id: int,
    user_id: int,
    notes: Optional[str],
    request_telegram_proof: bool = False,
) -> ChecklistItem:
    """Mark a checklist item as completed by a user."""
    from app.core.exceptions import NotFoundError

    result = await db.execute(select(ChecklistItem).where(ChecklistItem.id == item_id))
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundError("ChecklistItem", item_id)

    now = datetime.now(timezone.utc)
    task.is_completed = True
    task.completed_at = now
    task.completed_by_user_id = user_id
    if notes:
        task.completion_notes = notes
    if request_telegram_proof:
        task.photo_requested_via_telegram = True

    return task
