"""
Checklist service — weekly checklist generation and management.

Checklists are auto-generated every Monday for each of the 4 groups.
Return tasks are auto-created when items/bins are checked out and
auto-completed when they are returned.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bin_transaction import BinTransaction
from app.models.checklist import Checklist, ChecklistAssignment, ChecklistItem, GroupName
from app.models.item import Item
from app.models.transaction import Transaction
from app.models.user import User

log = logging.getLogger(__name__)


def _current_week_monday() -> date:
    """Return the Monday of the current week."""
    today = date.today()
    return today - timedelta(days=today.weekday())


async def get_or_create_weekly_checklists(db: AsyncSession) -> list[Checklist]:
    """
    Ensure one checklist exists for each group for the current week.
    Called on Monday morning by the scheduler and lazily on first access.
    Returns the list of current-week checklists (creating any that are missing).
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
    return checklist


async def add_return_task_for_transaction(
    db: AsyncSession,
    transaction: Transaction,
    user: User,
) -> Optional[ChecklistItem]:
    """
    When a non-consumable item is checked out, add a return task to the
    borrower's group's current-week checklist.
    Returns the created ChecklistItem, or None if user has no group.
    """
    if not user.group_name:
        return None

    checklist = await get_current_checklist_for_group(db, user.group_name)
    if not checklist:
        return None

    item_result = await db.execute(select(Item).where(Item.id == transaction.item_id))
    item = item_result.scalar_one_or_none()
    item_name = item.name if item else f"Item #{transaction.item_id}"

    # Count existing items to set order
    count_result = await db.execute(
        select(ChecklistItem).where(ChecklistItem.checklist_id == checklist.id)
    )
    existing_count = len(list(count_result.scalars().all()))

    task = ChecklistItem(
        checklist_id=checklist.id,
        title=f"Return: {item_name} (×{transaction.quantity})",
        description=f"Return '{item_name}' checked out by {user.full_name}",
        item_order=existing_count,
        is_auto_generated=True,
        auto_type="ITEM_RETURN",
        linked_transaction_id=transaction.id,
    )
    db.add(task)
    await db.flush()
    log.info("Auto-created return task: checklist=%d txn=%d item=%s", checklist.id, transaction.id, item_name)
    return task


async def add_return_task_for_bin_transaction(
    db: AsyncSession,
    bin_transaction: BinTransaction,
    user: User,
) -> Optional[ChecklistItem]:
    """
    When a bin is checked out, add a return task to the borrower's group's
    current-week checklist.
    Returns the created ChecklistItem, or None if user has no group.
    """
    if not user.group_name:
        return None

    checklist = await get_current_checklist_for_group(db, user.group_name)
    if not checklist:
        return None

    from app.models.bin import Bin
    bin_result = await db.execute(select(Bin).where(Bin.id == bin_transaction.bin_id))
    bin_obj = bin_result.scalar_one_or_none()
    bin_label = bin_obj.label if bin_obj else f"Bin #{bin_transaction.bin_id}"

    count_result = await db.execute(
        select(ChecklistItem).where(ChecklistItem.checklist_id == checklist.id)
    )
    existing_count = len(list(count_result.scalars().all()))

    task = ChecklistItem(
        checklist_id=checklist.id,
        title=f"Return Bin: {bin_label}",
        description=f"Return bin '{bin_label}' checked out by {user.full_name}",
        item_order=existing_count,
        is_auto_generated=True,
        auto_type="BIN_RETURN",
        linked_bin_transaction_id=bin_transaction.id,
    )
    db.add(task)
    await db.flush()
    log.info("Auto-created bin return task: checklist=%d bin_txn=%d", checklist.id, bin_transaction.id)
    return task


async def auto_complete_return_task_for_transaction(
    db: AsyncSession,
    transaction_id: int,
    returned_by_user_id: int,
) -> Optional[ChecklistItem]:
    """
    When an item transaction is returned, find and mark the corresponding
    auto-generated return task as completed.
    Returns the completed ChecklistItem or None.
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
    Returns the completed ChecklistItem or None.
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
