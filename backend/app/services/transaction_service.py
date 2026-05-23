"""
Transaction service — the core business logic layer.

All checkout, return, and overdue operations go through this module.
It updates Item.quantity_available atomically with the transaction record
and delegates Telegram notifications to telegram_service.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import InsufficientStockError, NotFoundError, PermissionDeniedError, TransactionConflictError
from app.models.activity_log import ActivityType
from app.models.bin import Bin
from app.models.bin_transaction import BinTransaction, BinTransactionStatus
from app.models.item import Item
from app.models.transaction import CheckoutPurpose, Transaction, TransactionStatus
from app.models.user import User
from app.services.activity_service import log_activity

log = logging.getLogger(__name__)


async def checkout_item(
    db: AsyncSession,
    *,
    item_id: int,
    user_id: int,
    processed_by_user_id: int,
    quantity: float,
    due_at: Optional[datetime],
    notes: Optional[str],
    bypass_requires_request: bool = False,
    purpose: str = CheckoutPurpose.GENERAL,
) -> Transaction:
    """
    Creates a CHECKED_OUT transaction and decrements Item.quantity_available.
    Raises InsufficientStockError if quantity > available.
    Raises NotFoundError if item or user does not exist / is inactive.
    """
    # Load item with lock to prevent race conditions on quantity
    result = await db.execute(
        select(Item).where(Item.id == item_id, Item.is_active == True).with_for_update()
    )
    item = result.scalar_one_or_none()
    if not item:
        raise NotFoundError("Item", item_id)

    user_result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    if not user_result.scalar_one_or_none():
        raise NotFoundError("User", user_id)

    # If item is inside a bin, allow individual checkout ONLY if the bin is not
    # currently checked out as a whole. If the bin itself is checked out, the
    # item is already part of that bin transaction.
    if item.bin_id is not None:
        active_bin_txn = await db.execute(
            select(BinTransaction).where(
                BinTransaction.bin_id == item.bin_id,
                BinTransaction.status == BinTransactionStatus.CHECKED_OUT,
            )
        )
        if active_bin_txn.scalar_one_or_none():
            raise TransactionConflictError(
                f"Item '{item.name}' is inside a bin that is currently checked out as a whole. "
                "Return the bin first, or wait for the bin to be returned."
            )

    # Block individual checkout when the bin enforces full-bin checkout only
    if item.bin_id is not None:
        bin_result = await db.execute(select(Bin).where(Bin.id == item.bin_id))
        bin_ = bin_result.scalar_one_or_none()
        if bin_ and bin_.requires_full_bin_checkout:
            raise TransactionConflictError(
                f"Item '{item.name}' belongs to a bin that must be checked out as a whole. "
                "Please check out the full bin instead."
            )

    if item.requires_request and not bypass_requires_request:
        raise PermissionDeniedError(
            f"Item '{item.name}' must be requested before checkout. "
            "Please submit a request to check out this item."
        )

    if item.is_consumable:
        raise TransactionConflictError(
            f"Item '{item.name}' is consumable. Use mark-as-used instead of checkout."
        )

    qty = Decimal(str(quantity)) if not isinstance(quantity, Decimal) else quantity
    if item.quantity_available < qty:
        raise InsufficientStockError(item.name, qty, item.quantity_available)

    item.quantity_available -= qty

    transaction = Transaction(
        item_id=item_id,
        user_id=user_id,
        processed_by_user_id=processed_by_user_id,
        quantity=qty,
        status=TransactionStatus.CHECKED_OUT,
        due_at=due_at,
        notes=notes,
        purpose=purpose,
    )
    db.add(transaction)
    await db.flush()  # get transaction.id without committing
    await db.refresh(transaction)

    await log_activity(
        db,
        activity_type=ActivityType.ITEM_CHECKED_OUT,
        actor_id=processed_by_user_id,
        target_item_id=item_id,
        target_cabinet_id=item.cabinet_id,
        quantity_delta=float(-qty),
        notes=notes,
        metadata={"status": TransactionStatus.CHECKED_OUT, "due_at": due_at.isoformat() if due_at else None},
        source_type="transaction",
        source_id=transaction.id,
    )

    log.info(
        "Checkout: transaction=%d item=%d user=%d qty=%d",
        transaction.id,
        item_id,
        user_id,
        quantity,
    )
    return transaction


async def return_item(
    db: AsyncSession,
    *,
    transaction_id: int,
    processed_by_user_id: int,
    notes: Optional[str],
    requesting_user_id: int,
) -> Transaction:
    """
    Marks a transaction RETURNED and increments Item.quantity_available.
    Only the transaction's owner or a user with can_process_any_transaction
    may return — enforcement happens in the router via permissions module.
    Sets photo_requested_via_telegram=True (Telegram notification is sent
    by the router after commit).
    """
    result = await db.execute(
        select(Transaction)
        .where(Transaction.id == transaction_id)
        .options(selectinload(Transaction.item), selectinload(Transaction.user))
        .with_for_update()
    )
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise NotFoundError("Transaction", transaction_id)

    if transaction.status in (TransactionStatus.RETURNED, TransactionStatus.CANCELLED):
        raise TransactionConflictError(
            f"Transaction {transaction_id} is already {transaction.status}"
        )

    item_result = await db.execute(
        select(Item).where(Item.id == transaction.item_id).with_for_update()
    )
    item = item_result.scalar_one()

    transaction.status = TransactionStatus.RETURNED
    transaction.returned_at = datetime.now(timezone.utc)
    transaction.processed_by_user_id = processed_by_user_id
    transaction.photo_requested_via_telegram = True  # bot will send photo request
    if notes:
        transaction.notes = (transaction.notes or "") + f"\n[Return] {notes}"

    item.quantity_available += transaction.quantity

    await log_activity(
        db,
        activity_type=ActivityType.ITEM_RETURNED,
        actor_id=processed_by_user_id,
        target_item_id=transaction.item_id,
        target_cabinet_id=item.cabinet_id,
        quantity_delta=float(transaction.quantity),
        notes=notes,
        source_type="transaction",
        source_id=transaction.id,
    )

    log.info(
        "Return: transaction=%d item=%d user=%d qty=%s",
        transaction.id,
        transaction.item_id,
        transaction.user_id,
        transaction.quantity,
    )
    return transaction


async def cancel_transaction(
    db: AsyncSession,
    *,
    transaction_id: int,
    processed_by_user_id: int,
) -> Transaction:
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id).with_for_update()
    )
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise NotFoundError("Transaction", transaction_id)

    if transaction.status in (TransactionStatus.RETURNED, TransactionStatus.CANCELLED):
        raise TransactionConflictError(
            f"Cannot cancel transaction with status {transaction.status}"
        )

    item_result = await db.execute(
        select(Item).where(Item.id == transaction.item_id).with_for_update()
    )
    item = item_result.scalar_one()

    transaction.status = TransactionStatus.CANCELLED
    transaction.processed_by_user_id = processed_by_user_id
    item.quantity_available += transaction.quantity

    return transaction


async def mark_overdue_transactions(db: AsyncSession) -> int:
    """
    Background task: marks CHECKED_OUT transactions past due_at as OVERDUE.
    Returns the number of records updated.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(Transaction)
        .where(
            Transaction.status == TransactionStatus.CHECKED_OUT,
            Transaction.due_at != None,
            Transaction.due_at < now,
        )
        .values(status=TransactionStatus.OVERDUE)
        .returning(Transaction.id)
    )
    updated_ids = result.scalars().all()
    if updated_ids:
        log.info("Marked %d transactions as OVERDUE: %s", len(updated_ids), updated_ids)
    return len(updated_ids)
