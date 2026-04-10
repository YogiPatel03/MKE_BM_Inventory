from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.permissions import can_process_transaction_for, require_view_all_transactions
from app.dependencies import get_current_user, get_db
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User
from app.schemas.transaction import (
    CheckoutRequest,
    ReturnRequest,
    TransactionDetail,
    TransactionOut,
)
from app.services import telegram_service
from app.services.checklist_service import (
    add_return_task_for_transaction,
    auto_complete_return_task_for_transaction,
)
from app.services.transaction_service import (
    cancel_transaction,
    checkout_item,
    return_item,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=list[TransactionOut])
async def list_transactions(
    status_filter: str | None = None,
    user_id_filter: int | None = None,
    item_id_filter: int | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Transaction]:
    query = select(Transaction)

    # Non-privileged users only see their own transactions
    if not (current_user.role.can_view_all_transactions or current_user.role.can_manage_users):
        query = query.where(Transaction.user_id == current_user.id)
    elif user_id_filter:
        query = query.where(Transaction.user_id == user_id_filter)

    if status_filter:
        query = query.where(Transaction.status == status_filter)
    if item_id_filter:
        query = query.where(Transaction.item_id == item_id_filter)

    query = query.order_by(Transaction.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("/checkout", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
async def checkout(
    body: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Transaction:
    if not can_process_transaction_for(current_user, body.user_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You can only check out items for yourself unless you have coordinator permissions",
        )

    transaction = await checkout_item(
        db,
        item_id=body.item_id,
        user_id=body.user_id,
        processed_by_user_id=current_user.id,
        quantity=body.quantity,
        due_at=body.due_at,
        notes=body.notes,
    )
    # Auto-create return task on the borrower's group checklist
    from sqlalchemy import select as sa_select
    from app.models.user import User as UserModel
    borrower_result = await db.execute(sa_select(UserModel).where(UserModel.id == body.user_id))
    borrower = borrower_result.scalar_one_or_none()
    if borrower:
        await add_return_task_for_transaction(db, transaction, borrower)

    await db.commit()

    # Load relationships for notification
    await db.refresh(transaction, ["item", "user"])
    await telegram_service.notify_checkout(transaction)

    return transaction


@router.post("/{transaction_id}/return", response_model=TransactionOut)
async def return_transaction(
    transaction_id: int,
    body: ReturnRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Transaction:
    # Peek at the transaction to check ownership before locking
    peek = await db.execute(
        select(Transaction.user_id).where(Transaction.id == transaction_id)
    )
    row = peek.one_or_none()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")

    if not can_process_transaction_for(current_user, row[0]):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You can only return items for yourself unless you have coordinator permissions",
        )

    transaction = await return_item(
        db,
        transaction_id=transaction_id,
        processed_by_user_id=current_user.id,
        notes=body.notes,
        requesting_user_id=current_user.id,
    )

    # Auto-complete the corresponding checklist return task
    await auto_complete_return_task_for_transaction(db, transaction_id, current_user.id)

    await db.commit()

    await db.refresh(transaction, ["item", "user"])
    request_msg_id = await telegram_service.notify_return_and_request_photo(transaction)
    if request_msg_id:
        transaction.photo_request_message_id = request_msg_id
        await db.commit()

    await db.refresh(transaction)
    return transaction


@router.post("/{transaction_id}/cancel", response_model=TransactionOut)
async def cancel(
    transaction_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Transaction:
    # Only coordinators/admins can cancel
    if not (current_user.role.can_process_any_transaction or current_user.role.can_manage_users):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Coordinator permission required to cancel")

    transaction = await cancel_transaction(
        db,
        transaction_id=transaction_id,
        processed_by_user_id=current_user.id,
    )
    await db.commit()
    await db.refresh(transaction)
    return transaction


@router.get("/{transaction_id}", response_model=TransactionDetail)
async def get_transaction(
    transaction_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Transaction:
    result = await db.execute(
        select(Transaction)
        .where(Transaction.id == transaction_id)
        .options(
            selectinload(Transaction.item),
            selectinload(Transaction.user).selectinload(User.role),
            selectinload(Transaction.processed_by).selectinload(User.role),
        )
    )
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")

    # Users can only view their own transactions unless they have elevated access
    if transaction.user_id != current_user.id and not (
        current_user.role.can_view_all_transactions or current_user.role.can_manage_users
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")

    return transaction
