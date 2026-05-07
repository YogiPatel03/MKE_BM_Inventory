import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

log = logging.getLogger(__name__)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user as get_current_active_user, get_db
from app.core.permissions import is_group_lead, require_process_any_transaction
from app.models.bin_transaction import BinTransaction
from app.models.user import User
from app.schemas.bin_transaction import BinCheckoutOut, BinTransactionCreate, BinTransactionOut, BinTransactionReturn
from app.services import telegram_service
from app.services.bin_transaction_service import checkout_bin, return_bin
from app.services.checklist_service import (
    add_return_task_for_bin_transaction,
    auto_complete_return_task_for_bin,
)

router = APIRouter(prefix="/bin-transactions", tags=["bin-transactions"])


@router.post("", response_model=BinCheckoutOut, status_code=201)
async def checkout_bin_endpoint(
    body: BinTransactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Bin checkout is self-service: any authenticated user can check out for themselves.
    # No extra permission check needed — get_current_active_user already ensures authentication.
    bin_txn, excluded_item_ids = await checkout_bin(
        db,
        bin_id=body.bin_id,
        user_id=current_user.id,
        processed_by_user_id=current_user.id,
        due_at=body.due_at,
        notes=body.notes,
    )

    # Auto-create return task on the user's group checklist
    await add_return_task_for_bin_transaction(db, bin_txn, current_user)

    await db.commit()
    await db.refresh(bin_txn, ["bin", "user"])
    try:
        await telegram_service.notify_bin_checkout(bin_txn)
    except Exception:
        log.warning("Bin checkout notification failed for bin_txn_id=%s", bin_txn.id)
    return BinCheckoutOut(
        **{k: v for k, v in bin_txn.__dict__.items() if not k.startswith("_")},
        excluded_item_ids=excluded_item_ids,
    )


@router.post("/{bin_transaction_id}/return", response_model=BinTransactionOut)
async def return_bin_endpoint(
    bin_transaction_id: int,
    body: BinTransactionReturn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Load the existing bin transaction to check ownership
    existing = (await db.execute(
        select(BinTransaction).where(BinTransaction.id == bin_transaction_id)
    )).scalar_one_or_none()
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bin transaction not found")

    is_owner = existing.user_id == current_user.id
    is_coordinator = current_user.role.can_process_any_transaction or current_user.role.can_manage_users

    # GROUP_LEAD: allowed only if borrower is in their group
    is_group_lead_for_borrower = False
    if is_group_lead(current_user) and not is_coordinator:
        borrower = (await db.execute(select(User).where(User.id == existing.user_id))).scalar_one_or_none()
        if borrower and borrower.group_name == current_user.group_name:
            is_group_lead_for_borrower = True

    if not (is_owner or is_coordinator or is_group_lead_for_borrower):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only return bins you checked out")

    bin_txn = await return_bin(
        db,
        bin_transaction_id=bin_transaction_id,
        processed_by_user_id=current_user.id,
        notes=body.notes,
    )

    # Auto-complete the corresponding checklist return task
    await auto_complete_return_task_for_bin(db, bin_transaction_id, current_user.id)

    await db.commit()
    await db.refresh(bin_txn, ["bin", "user"])
    try:
        await telegram_service.notify_bin_return(bin_txn)
    except Exception:
        log.warning("Bin return notification failed for bin_txn_id=%s", bin_txn.id)
    return bin_txn


@router.get("", response_model=List[BinTransactionOut])
async def list_bin_transactions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = select(BinTransaction).order_by(BinTransaction.checked_out_at.desc()).limit(200)

    if current_user.role.can_process_any_transaction or current_user.role.can_manage_users:
        pass  # coordinators/admins see all
    elif is_group_lead(current_user):
        query = query.join(User, BinTransaction.user_id == User.id).where(
            User.group_name == current_user.group_name
        )
    else:
        query = query.where(BinTransaction.user_id == current_user.id)

    result = await db.execute(query)
    return result.scalars().all()
