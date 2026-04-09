from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user as get_current_active_user, get_db
from app.core.permissions import require_approve_requests
from app.models.inventory_request import InventoryRequest, RequestStatus
from app.models.user import User
from app.schemas.inventory_request import (
    InventoryRequestApprove,
    InventoryRequestCreate,
    InventoryRequestDeny,
    InventoryRequestOut,
)
from app.services.request_service import (
    approve_request,
    cancel_request,
    create_request,
    deny_request,
)
from app.services.telegram_service import notify_new_request

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("", response_model=InventoryRequestOut, status_code=201)
async def submit_request(
    body: InventoryRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.bin import Bin
    from app.models.item import Item

    req = await create_request(
        db,
        requester_id=current_user.id,
        item_id=body.item_id,
        bin_id=body.bin_id,
        quantity_requested=body.quantity_requested,
        reason=body.reason,
        due_at=body.due_at,
    )
    await db.commit()
    await db.refresh(req)

    # Fire-and-forget Telegram notification
    target_name = "Unknown"
    if body.item_id:
        result = await db.execute(select(Item).where(Item.id == body.item_id))
        item = result.scalar_one_or_none()
        if item:
            target_name = item.name
    elif body.bin_id:
        result = await db.execute(select(Bin).where(Bin.id == body.bin_id))
        bin_obj = result.scalar_one_or_none()
        if bin_obj:
            target_name = f"Bin: {bin_obj.label}"

    msg_id = await notify_new_request(req.id, current_user.username, target_name, body.reason)
    if msg_id:
        req.telegram_message_id = msg_id
        await db.commit()

    return req


@router.get("", response_model=List[InventoryRequestOut])
async def list_requests(
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = select(InventoryRequest).order_by(InventoryRequest.created_at.desc())

    # Non-approvers only see their own requests
    if not (current_user.role.can_approve_requests or current_user.role.can_manage_users):
        query = query.where(InventoryRequest.requester_id == current_user.id)

    if status:
        query = query.where(InventoryRequest.status == status)

    result = await db.execute(query.limit(200))
    return result.scalars().all()


@router.post("/{request_id}/approve", response_model=InventoryRequestOut)
async def approve(
    request_id: int,
    body: InventoryRequestApprove,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_approve_requests(current_user)
    req = await approve_request(
        db,
        request_id=request_id,
        approver_id=current_user.id,
        due_at=body.due_at,
    )
    await db.commit()
    await db.refresh(req)
    return req


@router.post("/{request_id}/deny", response_model=InventoryRequestOut)
async def deny(
    request_id: int,
    body: InventoryRequestDeny,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_approve_requests(current_user)
    req = await deny_request(
        db,
        request_id=request_id,
        approver_id=current_user.id,
        denial_reason=body.denial_reason,
    )
    await db.commit()
    await db.refresh(req)
    return req


@router.post("/{request_id}/cancel", response_model=InventoryRequestOut)
async def cancel(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    req = await cancel_request(db, request_id=request_id, user_id=current_user.id)
    await db.commit()
    await db.refresh(req)
    return req
