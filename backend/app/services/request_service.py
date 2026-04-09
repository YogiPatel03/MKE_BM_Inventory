"""
Request/approval workflow service.

USER role creates InventoryRequests. GROUP_LEAD+ approves or denies.
On approval, can optionally auto-fulfill (create the transaction immediately).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, TransactionConflictError
from app.models.inventory_request import InventoryRequest, RequestStatus
from app.models.item import Item
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
    result = await db.execute(
        select(InventoryRequest).where(InventoryRequest.id == request_id).with_for_update()
    )
    req = result.scalar_one_or_none()
    if not req:
        raise NotFoundError("InventoryRequest", request_id)

    if req.status != RequestStatus.PENDING:
        raise TransactionConflictError(f"Request {request_id} is already {req.status}")

    req.status = RequestStatus.APPROVED
    req.approver_id = approver_id
    req.approved_at = datetime.now(timezone.utc)
    if due_at:
        req.due_at = due_at

    await db.flush()
    await db.refresh(req)
    log.info("Request approved: req=%d by=%d", req.id, approver_id)
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
