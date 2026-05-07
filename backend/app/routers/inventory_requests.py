import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user as get_current_active_user, get_db
from app.core.permissions import check_request_scope, is_group_lead, require_approve_requests

log = logging.getLogger(__name__)
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
from app.services.telegram_service import (
    notify_new_request,
    notify_request_approved,
    notify_request_denied,
)

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

    # DM the requester to confirm submission — non-fatal.
    try:
        if current_user.telegram_chat_id:
            from app.services.telegram_service import notify_request_submitted
            await notify_request_submitted(current_user.telegram_chat_id, target_name, req.id)
    except Exception:
        log.warning("Failed to send submission notification for request %d", req.id)

    return req


@router.get("", response_model=List[InventoryRequestOut])
async def list_requests(
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = select(InventoryRequest).order_by(InventoryRequest.created_at.desc())

    if current_user.role.can_manage_users:
        pass  # admins see all
    elif is_group_lead(current_user):
        # GROUP_LEAD sees only their own group's requests
        query = query.join(User, InventoryRequest.requester_id == User.id).where(
            User.group_name == current_user.group_name
        )
    elif not current_user.role.can_approve_requests:
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

    # Scope check: group leads may only approve requests from their own group.
    # Mirrors the same visibility rule used by list_requests.
    scope_row = (await db.execute(
        select(User.group_name)
        .select_from(InventoryRequest)
        .join(User, User.id == InventoryRequest.requester_id)
        .where(InventoryRequest.id == request_id)
    )).first()
    if scope_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")
    if not check_request_scope(current_user, scope_row[0]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to approve requests from this group.",
        )

    req = await approve_request(
        db,
        request_id=request_id,
        approver_id=current_user.id,
        due_at=body.due_at,
    )
    await db.commit()
    await db.refresh(req)

    # Notify requester via Telegram DM — non-fatal: a notification failure must
    # never mask or roll back a successful approval that is already committed.
    try:
        from app.models.item import Item
        from app.models.bin import Bin
        requester = (await db.execute(
            select(User).where(User.id == req.requester_id)
        )).scalar_one_or_none()
        if requester and requester.telegram_chat_id:
            target_name = "unknown item"
            if req.item_id:
                item = (await db.execute(select(Item).where(Item.id == req.item_id))).scalar_one_or_none()
                if item:
                    target_name = item.name
            elif req.bin_id:
                bin_obj = (await db.execute(select(Bin).where(Bin.id == req.bin_id))).scalar_one_or_none()
                if bin_obj:
                    target_name = f"Bin: {bin_obj.label}"
            await notify_request_approved(requester.telegram_chat_id, target_name, req.id)
    except Exception:
        log.warning("Failed to send approval notification for request %d", req.id)

    return req


@router.post("/{request_id}/deny", response_model=InventoryRequestOut)
async def deny(
    request_id: int,
    body: InventoryRequestDeny,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_approve_requests(current_user)

    # Scope check: mirrors the same rule as approve.
    scope_row = (await db.execute(
        select(User.group_name)
        .select_from(InventoryRequest)
        .join(User, User.id == InventoryRequest.requester_id)
        .where(InventoryRequest.id == request_id)
    )).first()
    if scope_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")
    if not check_request_scope(current_user, scope_row[0]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to deny requests from this group.",
        )

    req = await deny_request(
        db,
        request_id=request_id,
        approver_id=current_user.id,
        denial_reason=body.denial_reason,
    )
    await db.commit()
    await db.refresh(req)

    # Non-fatal notification — must not mask a successful denial.
    try:
        from app.models.item import Item
        from app.models.bin import Bin
        requester = (await db.execute(
            select(User).where(User.id == req.requester_id)
        )).scalar_one_or_none()
        if requester and requester.telegram_chat_id:
            target_name = "unknown item"
            if req.item_id:
                item = (await db.execute(select(Item).where(Item.id == req.item_id))).scalar_one_or_none()
                if item:
                    target_name = item.name
            elif req.bin_id:
                bin_obj = (await db.execute(select(Bin).where(Bin.id == req.bin_id))).scalar_one_or_none()
                if bin_obj:
                    target_name = f"Bin: {bin_obj.label}"
            await notify_request_denied(requester.telegram_chat_id, target_name, req.id, body.denial_reason)
    except Exception:
        log.warning("Failed to send denial notification for request %d", req.id)

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
