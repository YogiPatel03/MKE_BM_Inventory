"""
Bin transaction service — checkout/return of all items in a bin as a unit.

When a bin is checked out:
  1. A BinTransaction record is created.
  2. For every active item in the bin with quantity_available > 0, a Transaction
     record is created and linked via bin_transaction_id.
  3. Item.quantity_available is decremented for each item.

Return reverses this: all linked CHECKED_OUT/OVERDUE transactions are RETURNED
and quantities are restored.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, TransactionConflictError
from app.models.activity_log import ActivityType
from app.models.bin import Bin
from app.models.bin_transaction import BinTransaction, BinTransactionStatus
from app.models.item import Item
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User
from app.services.activity_service import log_activity

log = logging.getLogger(__name__)


async def checkout_bin(
    db: AsyncSession,
    *,
    bin_id: int,
    user_id: int,
    processed_by_user_id: int,
    due_at: Optional[datetime],
    notes: Optional[str],
) -> BinTransaction:
    # Verify bin exists
    bin_result = await db.execute(
        select(Bin)
        .where(Bin.id == bin_id)
        .options(selectinload(Bin.items))
        .with_for_update()
    )
    bin_obj = bin_result.scalar_one_or_none()
    if not bin_obj:
        raise NotFoundError("Bin", bin_id)

    # Verify user exists
    user_result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    if not user_result.scalar_one_or_none():
        raise NotFoundError("User", user_id)

    # Check no active bin transaction already exists
    existing = await db.execute(
        select(BinTransaction).where(
            BinTransaction.bin_id == bin_id,
            BinTransaction.status == BinTransactionStatus.CHECKED_OUT,
        )
    )
    if existing.scalar_one_or_none():
        raise TransactionConflictError(f"Bin {bin_id} is already checked out.")

    bin_txn = BinTransaction(
        bin_id=bin_id,
        user_id=user_id,
        processed_by_user_id=processed_by_user_id,
        status=BinTransactionStatus.CHECKED_OUT,
        due_at=due_at,
        notes=notes,
    )
    db.add(bin_txn)
    await db.flush()  # get bin_txn.id

    # Create individual transactions for all active items in the bin
    active_items = [i for i in bin_obj.items if i.is_active and i.quantity_available > 0]
    for item in active_items:
        # Lock item row
        item_result = await db.execute(
            select(Item).where(Item.id == item.id).with_for_update()
        )
        locked_item = item_result.scalar_one()
        qty = locked_item.quantity_available
        locked_item.quantity_available = 0  # check out all available units

        txn = Transaction(
            item_id=locked_item.id,
            user_id=user_id,
            processed_by_user_id=processed_by_user_id,
            quantity=qty,
            status=TransactionStatus.CHECKED_OUT,
            due_at=due_at,
            notes=f"[Bin checkout #{bin_txn.id}] {notes or ''}".strip(),
            bin_transaction_id=bin_txn.id,
        )
        db.add(txn)

    await db.flush()
    await db.refresh(bin_txn)

    await log_activity(
        db,
        activity_type=ActivityType.BIN_CHECKED_OUT,
        actor_id=processed_by_user_id,
        target_bin_id=bin_id,
        target_cabinet_id=bin_obj.cabinet_id,
        notes=notes,
        metadata={"bin_transaction_id": bin_txn.id, "item_count": len(active_items)},
        source_type="bin_transaction",
        source_id=bin_txn.id,
    )

    log.info("BinCheckout: bin_txn=%d bin=%d user=%d items=%d", bin_txn.id, bin_id, user_id, len(active_items))
    return bin_txn


async def return_bin(
    db: AsyncSession,
    *,
    bin_transaction_id: int,
    processed_by_user_id: int,
    notes: Optional[str],
) -> BinTransaction:
    result = await db.execute(
        select(BinTransaction)
        .where(BinTransaction.id == bin_transaction_id)
        .options(selectinload(BinTransaction.transactions))
        .with_for_update()
    )
    bin_txn = result.scalar_one_or_none()
    if not bin_txn:
        raise NotFoundError("BinTransaction", bin_transaction_id)

    if bin_txn.status in (BinTransactionStatus.RETURNED, BinTransactionStatus.CANCELLED):
        raise TransactionConflictError(
            f"BinTransaction {bin_transaction_id} is already {bin_txn.status}"
        )

    now = datetime.now(timezone.utc)
    bin_txn.status = BinTransactionStatus.RETURNED
    bin_txn.returned_at = now
    bin_txn.processed_by_user_id = processed_by_user_id
    if notes:
        bin_txn.notes = (bin_txn.notes or "") + f"\n[Return] {notes}"

    # Return all linked transactions and restore quantities
    for txn in bin_txn.transactions:
        if txn.status in (TransactionStatus.CHECKED_OUT, TransactionStatus.OVERDUE):
            item_result = await db.execute(
                select(Item).where(Item.id == txn.item_id).with_for_update()
            )
            item = item_result.scalar_one()
            item.quantity_available += txn.quantity
            txn.status = TransactionStatus.RETURNED
            txn.returned_at = now
            txn.processed_by_user_id = processed_by_user_id

    await db.flush()
    await db.refresh(bin_txn)

    await log_activity(
        db,
        activity_type=ActivityType.BIN_RETURNED,
        actor_id=processed_by_user_id,
        target_bin_id=bin_txn.bin_id,
        notes=notes,
        source_type="bin_transaction",
        source_id=bin_txn.id,
    )

    log.info("BinReturn: bin_txn=%d bin=%d", bin_txn.id, bin_txn.bin_id)
    return bin_txn
