"""
Request/approval workflow service.

USER role creates InventoryRequests. GROUP_LEAD+ approves or denies.
On approval, approval auto-fulfills: a Transaction or BinTransaction is
created immediately, and the request status advances to FULFILLED.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, TransactionConflictError
from app.models.bin_transaction import BinTransaction, BinTransactionStatus
from app.models.inventory_request import InventoryRequest, RequestStatus
from app.models.item import Item
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User

log = logging.getLogger(__name__)


async def create_request(
    db: AsyncSession,
    *,
    requester_id: int,
    item_id: Optional[int],
    bin_id: Optional[int],
    quantity_requested: int,
    reason: Optional[str],
    due_at: Optional[datetime],
) -> InventoryRequest:
    # Verify target exists
    if item_id:
        result = await db.execute(select(Item).where(Item.id == item_id, Item.is_active == True))
        if not result.scalar_one_or_none():
            raise NotFoundError("Item", item_id)

    req = InventoryRequest(
        requester_id=requester_id,
        item_id=item_id,
        bin_id=bin_id,
        quantity_requested=quantity_requested,
        reason=reason,
        due_at=due_at,
        status=RequestStatus.PENDING,
    )
    db.add(req)
    await db.flush()
    await db.refresh(req)
    log.info("Request created: req=%d by=%d", req.id, requester_id)
    return req


async def approve_request(
    db: AsyncSession,
    *,
    request_id: int,
    approver_id: int,
    due_at: Optional[datetime],
) -> InventoryRequest:
    """
    Approve a pending request and immediately fulfill it:
    - Item requests → create a Transaction (CHECKED_OUT)
    - Bin requests  → create a BinTransaction + child Transactions for bin items
    Status advances to FULFILLED (not just APPROVED).
    """
    result = await db.execute(
        select(InventoryRequest).where(InventoryRequest.id == request_id).with_for_update()
    )
    req = result.scalar_one_or_none()
    if not req:
        raise NotFoundError("InventoryRequest", request_id)

    if req.status != RequestStatus.PENDING:
        raise TransactionConflictError(f"Request {request_id} is already {req.status}")

    now = datetime.now(timezone.utc)
    effective_due_at = due_at or req.due_at

    req.approver_id = approver_id
    req.approved_at = now

    if req.item_id:
        # Fulfill item request → checkout transaction
        item_result = await db.execute(
            select(Item).where(Item.id == req.item_id, Item.is_active == True).with_for_update()
        )
        item = item_result.scalar_one_or_none()
        if not item:
            raise NotFoundError("Item", req.item_id)
        if item.quantity_available < req.quantity_requested:
            from app.core.exceptions import InsufficientStockError
            raise InsufficientStockError(item.name, req.quantity_requested, item.quantity_available)

        item.quantity_available -= req.quantity_requested
        txn = Transaction(
            item_id=req.item_id,
            user_id=req.requester_id,
            processed_by_user_id=approver_id,
            quantity=req.quantity_requested,
            status=TransactionStatus.CHECKED_OUT,
            due_at=effective_due_at,
            notes=f"[Fulfilled from request #{req.id}]",
        )
        db.add(txn)

    elif req.bin_id:
        # Fulfill bin request → bin checkout transaction + child item transactions
        from app.models.bin import Bin
        from sqlalchemy.orm import selectinload as sload

        bin_result = await db.execute(
            select(Bin)
            .where(Bin.id == req.bin_id)
            .options(sload(Bin.items))
            .with_for_update()
        )
        bin_obj = bin_result.scalar_one_or_none()
        if not bin_obj:
            raise NotFoundError("Bin", req.bin_id)

        # Check not already checked out
        existing = await db.execute(
            select(BinTransaction).where(
                BinTransaction.bin_id == req.bin_id,
                BinTransaction.status == BinTransactionStatus.CHECKED_OUT,
            )
        )
        if existing.scalar_one_or_none():
            raise TransactionConflictError(f"Bin {req.bin_id} is already checked out.")

        bin_txn = BinTransaction(
            bin_id=req.bin_id,
            user_id=req.requester_id,
            processed_by_user_id=approver_id,
            status=BinTransactionStatus.CHECKED_OUT,
            due_at=effective_due_at,
            notes=f"[Fulfilled from request #{req.id}]",
        )
        db.add(bin_txn)
        await db.flush()

        active_items = [i for i in bin_obj.items if i.is_active and i.quantity_available > 0]
        for item in active_items:
            item_result = await db.execute(
                select(Item).where(Item.id == item.id).with_for_update()
            )
            locked = item_result.scalar_one()
            qty = locked.quantity_available
            locked.quantity_available = 0
            db.add(Transaction(
                item_id=locked.id,
                user_id=req.requester_id,
                processed_by_user_id=approver_id,
                quantity=qty,
                status=TransactionStatus.CHECKED_OUT,
                due_at=effective_due_at,
                notes=f"[Bin checkout via request #{req.id}]",
                bin_transaction_id=bin_txn.id,
            ))

    req.status = RequestStatus.FULFILLED
    req.fulfilled_at = now

    await db.flush()
    await db.refresh(req)
    log.info("Request fulfilled: req=%d by=%d", req.id, approver_id)
    return req


async def deny_request(
    db: AsyncSession,
    *,
    request_id: int,
    approver_id: int,
    denial_reason: Optional[str],
) -> InventoryRequest:
    result = await db.execute(
        select(InventoryRequest).where(InventoryRequest.id == request_id).with_for_update()
    )
    req = result.scalar_one_or_none()
    if not req:
        raise NotFoundError("InventoryRequest", request_id)

    if req.status != RequestStatus.PENDING:
        raise TransactionConflictError(f"Request {request_id} is already {req.status}")

    req.status = RequestStatus.DENIED
    req.approver_id = approver_id
    req.denial_reason = denial_reason

    await db.flush()
    await db.refresh(req)
    log.info("Request denied: req=%d by=%d", req.id, approver_id)
    return req


async def cancel_request(
    db: AsyncSession,
    *,
    request_id: int,
    user_id: int,
) -> InventoryRequest:
    result = await db.execute(
        select(InventoryRequest).where(InventoryRequest.id == request_id).with_for_update()
    )
    req = result.scalar_one_or_none()
    if not req:
        raise NotFoundError("InventoryRequest", request_id)

    if req.requester_id != user_id:
        raise TransactionConflictError("Only the requester can cancel their request.")

    if req.status not in (RequestStatus.PENDING,):
        raise TransactionConflictError(f"Cannot cancel a request with status {req.status}")

    req.status = RequestStatus.CANCELLED

    await db.flush()
    await db.refresh(req)
    return req
