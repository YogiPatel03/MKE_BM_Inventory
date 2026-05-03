"""
Checklists router — weekly task checklists per group.

Permission model:
  - Admins / Coordinators: view all checklists, assign users, add items, delete manual items
  - Group Leads: view checklists for their own group (assigned OR same group_name — allows auto-return task visibility),
    add/edit/delete items only on checklists they are assigned to AND that belong to their own group,
    assign only same-group users
  - Users: view checklists for their own group, complete items only on assigned checklists
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_current_user, get_db
from app.models.checklist import (
    Checklist,
    ChecklistAssignment,
    ChecklistItem,
    GroupName,
    Subchecklist,
    SubchecklistType,
)
from app.models.user import User
from app.schemas.checklist import (
    ChecklistAssignCreate,
    ChecklistAssignmentOut,
    ChecklistItemComplete,
    ChecklistItemCreate,
    ChecklistItemOut,
    ChecklistItemUpdate,
    ChecklistOut,
    ChecklistSummary,
    SubchecklistCreate,
    SubchecklistOut,
)
from app.services.checklist_service import (
    complete_checklist_item,
    get_or_create_weekly_checklists,
)
from app.services.telegram_service import notify_checklist_return_proof

router = APIRouter(prefix="/checklists", tags=["checklists"])


def _can_manage(user: User) -> bool:
    return user.role.can_manage_users or user.role.can_manage_inventory


def _can_add_items(user: User) -> bool:
    """Coordinators, admins, and group leads can add items to checklists they're on."""
    return user.role.can_manage_users or user.role.can_manage_inventory or user.role.can_approve_requests


def _is_assigned(checklist: Checklist, user_id: int) -> bool:
    return any(a.user_id == user_id for a in checklist.assignments)


def _can_manage_tasks_on(user: User, checklist: Checklist) -> bool:
    """
    Admins/coordinators can manage tasks on any checklist.
    Group leads can manage tasks only on checklists they are assigned to AND that belong to their own group.
    """
    if _can_manage(user):
        return True
    if (
        user.role.can_approve_requests
        and _is_assigned(checklist, user.id)
        and user.group_name == checklist.group_name
    ):
        return True
    return False


@router.get("", response_model=List[ChecklistSummary])
async def list_checklists(
    group_name: Optional[str] = Query(None),
    week_start: Optional[str] = Query(None, description="YYYY-MM-DD Monday date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ChecklistSummary]:
    """
    List checklists. Admins/coordinators see all; others see only assigned ones.
    If no week_start given, defaults to current week (auto-generating if needed).
    """
    if not week_start:
        # Ensure current week checklists exist
        await get_or_create_weekly_checklists(db)
        await db.commit()

    query = (
        select(Checklist)
        .options(
            selectinload(Checklist.items),
            selectinload(Checklist.assignments),
        )
        .order_by(Checklist.week_start.desc(), Checklist.group_name)
    )

    if group_name and group_name in GroupName.ALL:
        query = query.where(Checklist.group_name == group_name)

    if week_start:
        from datetime import date
        try:
            ws = date.fromisoformat(week_start)
            query = query.where(Checklist.week_start == ws)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid week_start date format")

    rows = (await db.execute(query)).scalars().all()

    result = []
    for cl in rows:
        if (
            not _can_manage(current_user)
            and not _is_assigned(cl, current_user.id)
            and cl.group_name != current_user.group_name
        ):
            continue

        result.append(ChecklistSummary(
            id=cl.id,
            group_name=cl.group_name,
            week_start=cl.week_start,
            is_active=cl.is_active,
            created_at=cl.created_at,
            updated_at=cl.updated_at,
            item_count=len(cl.items),
            completed_count=sum(1 for i in cl.items if i.is_completed),
            assignee_count=len(cl.assignments),
        ))

    return result


@router.get("/{checklist_id}", response_model=ChecklistOut)
async def get_checklist(
    checklist_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChecklistOut:
    result = await db.execute(
        select(Checklist)
        .where(Checklist.id == checklist_id)
        .options(
            selectinload(Checklist.items).selectinload(ChecklistItem.assignee),
            selectinload(Checklist.assignments).selectinload(ChecklistAssignment.user),
            selectinload(Checklist.subchecklists).selectinload(Subchecklist.items),
        )
    )
    checklist = result.scalar_one_or_none()
    if not checklist:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Checklist not found")

    if (
        not _can_manage(current_user)
        and not _is_assigned(checklist, current_user.id)
        and checklist.group_name != current_user.group_name
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not assigned to this checklist")

    return checklist


@router.post("/{checklist_id}/items", response_model=ChecklistItemOut, status_code=status.HTTP_201_CREATED)
async def add_checklist_item(
    checklist_id: int,
    body: ChecklistItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChecklistItem:
    if not _can_add_items(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions to add checklist items")

    result = await db.execute(
        select(Checklist).where(Checklist.id == checklist_id)
        .options(selectinload(Checklist.assignments))
    )
    checklist = result.scalar_one_or_none()
    if not checklist:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Checklist not found")

    # Group leads can only add items to checklists they are on AND that belong to their own group
    if not _can_manage_tasks_on(current_user, checklist):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only add tasks to checklists you are assigned to in your own group")

    # Validate subchecklist if provided
    if body.subchecklist_id:
        sub_result = await db.execute(
            select(Subchecklist).where(
                Subchecklist.id == body.subchecklist_id,
                Subchecklist.checklist_id == checklist_id,
            )
        )
        if not sub_result.scalar_one_or_none():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Subchecklist not found in this checklist")

    # Validate assignee if provided: must be assigned to this checklist (unless admin)
    if body.assignee_id and not _can_manage(current_user):
        if not _is_assigned(checklist, body.assignee_id):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Assignee must be assigned to this checklist"
            )

    count_result = await db.execute(
        select(ChecklistItem).where(ChecklistItem.checklist_id == checklist_id)
    )
    existing_count = len(list(count_result.scalars().all()))

    item = ChecklistItem(
        checklist_id=checklist_id,
        subchecklist_id=body.subchecklist_id,
        title=body.title,
        description=body.description,
        item_order=body.item_order if body.item_order is not None else existing_count,
        assignee_id=body.assignee_id,
        is_auto_generated=False,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item, ["assignee"])
    return item


@router.patch("/{checklist_id}/items/{item_id}", response_model=ChecklistItemOut)
async def update_checklist_item(
    checklist_id: int,
    item_id: int,
    body: ChecklistItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChecklistItem:
    """Update title, description, or assignee of a checklist item."""
    cl_result = await db.execute(
        select(Checklist).where(Checklist.id == checklist_id)
        .options(selectinload(Checklist.assignments))
    )
    checklist = cl_result.scalar_one_or_none()
    if not checklist:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Checklist not found")

    if not _can_manage_tasks_on(current_user, checklist):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions to edit tasks on this checklist")

    item_result = await db.execute(
        select(ChecklistItem).where(
            ChecklistItem.id == item_id,
            ChecklistItem.checklist_id == checklist_id,
        )
    )
    task = item_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Checklist item not found")

    if body.title is not None:
        task.title = body.title
    if body.description is not None:
        task.description = body.description
    if body.assignee_id is not None:
        # Validate assignee is on this checklist (admins bypass)
        if not _can_manage(current_user):
            if not _is_assigned(checklist, body.assignee_id):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Assignee must be assigned to this checklist"
                )
        task.assignee_id = body.assignee_id

    await db.commit()
    await db.refresh(task, ["assignee"])
    return task


@router.patch("/{checklist_id}/items/{item_id}/complete", response_model=ChecklistItemOut)
async def complete_item(
    checklist_id: int,
    item_id: int,
    body: ChecklistItemComplete,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChecklistItem:
    """Mark a checklist item as completed. Assigned users can complete items."""
    cl_result = await db.execute(
        select(Checklist)
        .where(Checklist.id == checklist_id)
        .options(selectinload(Checklist.assignments))
    )
    checklist = cl_result.scalar_one_or_none()
    if not checklist:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Checklist not found")

    if not _can_manage(current_user) and not _is_assigned(checklist, current_user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You must be assigned to this checklist to complete tasks")

    item_result = await db.execute(
        select(ChecklistItem).where(
            ChecklistItem.id == item_id,
            ChecklistItem.checklist_id == checklist_id,
        )
    )
    task = item_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Checklist item not found")

    if (
        task.is_auto_generated
        and task.auto_type in ("ITEM_RETURN", "BIN_RETURN")
        and not task.is_completed
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Return the item through the checkout return flow first. "
            "This task will complete automatically when the return is processed.",
        )

    request_proof = task.is_auto_generated and task.auto_type in ("ITEM_RETURN", "BIN_RETURN")

    task = await complete_checklist_item(
        db,
        item_id=item_id,
        user_id=current_user.id,
        notes=body.notes,
        request_telegram_proof=request_proof,
    )

    await db.commit()
    await db.refresh(task)

    if request_proof:
        await notify_checklist_return_proof(task, current_user)

    return task


@router.delete("/{checklist_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_checklist_item(
    checklist_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Delete a manual (non-auto-generated) checklist item.
    Admins/coordinators can delete any manual task.
    Group leads can delete manual tasks on checklists they are assigned to.
    """
    cl_result = await db.execute(
        select(Checklist).where(Checklist.id == checklist_id)
        .options(selectinload(Checklist.assignments))
    )
    checklist = cl_result.scalar_one_or_none()
    if not checklist:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Checklist not found")

    if not _can_manage_tasks_on(current_user, checklist):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions to delete tasks on this checklist")

    item_result = await db.execute(
        select(ChecklistItem).where(
            ChecklistItem.id == item_id,
            ChecklistItem.checklist_id == checklist_id,
        )
    )
    task = item_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Checklist item not found")

    if task.is_auto_generated:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Auto-generated return tasks cannot be deleted. They auto-complete on return."
        )

    await db.delete(task)
    await db.commit()


@router.post("/{checklist_id}/subchecklists", response_model=SubchecklistOut, status_code=status.HTTP_201_CREATED)
async def create_subchecklist(
    checklist_id: int,
    body: SubchecklistCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Subchecklist:
    """Create a custom subchecklist within a checklist."""
    cl_result = await db.execute(
        select(Checklist).where(Checklist.id == checklist_id)
        .options(selectinload(Checklist.assignments))
    )
    checklist = cl_result.scalar_one_or_none()
    if not checklist:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Checklist not found")

    if not _can_manage_tasks_on(current_user, checklist):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")

    if body.section_type in (SubchecklistType.PRE_SABHA, SubchecklistType.POST_SABHA):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "PRE_SABHA and POST_SABHA subchecklists are created automatically"
        )

    # Determine order
    count_result = await db.execute(
        select(Subchecklist).where(Subchecklist.checklist_id == checklist_id)
    )
    existing_count = len(list(count_result.scalars().all()))

    sub = Subchecklist(
        checklist_id=checklist_id,
        title=body.title,
        section_type=SubchecklistType.CUSTOM,
        is_mandatory=False,
        section_order=body.section_order if body.section_order is not None else existing_count,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub, ["items"])
    return sub


@router.post("/{checklist_id}/assign", response_model=ChecklistAssignmentOut, status_code=status.HTTP_201_CREATED)
async def assign_user(
    checklist_id: int,
    body: ChecklistAssignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChecklistAssignment:
    """Assign a user to a checklist. Coordinators, admins, and group leads on this checklist."""
    cl_result = await db.execute(
        select(Checklist).where(Checklist.id == checklist_id)
        .options(selectinload(Checklist.assignments))
    )
    checklist = cl_result.scalar_one_or_none()
    if not checklist:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Checklist not found")

    # Admins/coordinators can assign to any checklist.
    # Group leads can assign only to checklists they are on AND that belong to their own group.
    if not _can_manage(current_user):
        if not (
            current_user.role.can_approve_requests
            and _is_assigned(checklist, current_user.id)
            and current_user.group_name == checklist.group_name
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions to assign users")

    target_user = (await db.execute(select(User).where(User.id == body.user_id, User.is_active == True))).scalar_one_or_none()
    if not target_user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    # Non-managers can only assign users within the same group as the checklist
    if not _can_manage(current_user):
        if target_user.group_name != checklist.group_name:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "You can only assign users from the same group as this checklist",
            )

    existing = await db.execute(
        select(ChecklistAssignment).where(
            ChecklistAssignment.checklist_id == checklist_id,
            ChecklistAssignment.user_id == body.user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "User is already assigned to this checklist")

    assignment = ChecklistAssignment(
        checklist_id=checklist_id,
        user_id=body.user_id,
        assigned_by_id=current_user.id,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment, ["user"])
    return assignment


@router.delete("/{checklist_id}/assign/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_user(
    checklist_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    cl_result = await db.execute(
        select(Checklist).where(Checklist.id == checklist_id)
        .options(selectinload(Checklist.assignments))
    )
    checklist = cl_result.scalar_one_or_none()
    if not checklist:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Checklist not found")

    if not _can_manage(current_user):
        if not (
            current_user.role.can_approve_requests
            and _is_assigned(checklist, current_user.id)
            and current_user.group_name == checklist.group_name
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions to unassign users")

    result = await db.execute(
        select(ChecklistAssignment).where(
            ChecklistAssignment.checklist_id == checklist_id,
            ChecklistAssignment.user_id == user_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found")

    await db.delete(assignment)
    await db.commit()


@router.post("/backfill-active-transactions", status_code=status.HTTP_200_OK)
async def backfill_active_transactions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Admin/coordinator only. Creates missing return tasks for any currently
    active (CHECKED_OUT / OVERDUE) transactions where the borrower has a
    group_name but no return task was created at checkout time.
    """
    if not _can_manage(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin or coordinator required")

    from app.models.transaction import Transaction, TransactionStatus
    from app.services.checklist_service import add_return_task_for_transaction

    txn_result = await db.execute(
        select(Transaction)
        .where(Transaction.status.in_([TransactionStatus.CHECKED_OUT, TransactionStatus.OVERDUE]))
        .options(selectinload(Transaction.user))
    )
    active_txns = txn_result.scalars().all()

    created = 0
    skipped = 0
    for txn in active_txns:
        borrower = txn.user
        if not borrower or not borrower.group_name:
            skipped += 1
            continue
        existing = await db.execute(
            select(ChecklistItem).where(
                ChecklistItem.linked_transaction_id == txn.id,
                ChecklistItem.is_auto_generated == True,
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue
        await add_return_task_for_transaction(db, txn, borrower)
        created += 1

    await db.commit()
    return {"created": created, "skipped": skipped}
