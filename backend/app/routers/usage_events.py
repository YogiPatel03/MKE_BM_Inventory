from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user as get_current_active_user, get_db
from app.models.usage_event import UsageEvent
from app.models.user import User
from app.schemas.usage_event import UsageEventCreate, UsageEventOut, UsageEventReverseRequest
from app.services.usage_service import mark_as_used, reverse_usage

router = APIRouter(prefix="/usage-events", tags=["usage-events"])


@router.post("", response_model=UsageEventOut, status_code=201)
async def create_usage_event(
    body: UsageEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    event = await mark_as_used(
        db,
        item_id=body.item_id,
        user_id=current_user.id,
        processed_by_user_id=current_user.id,
        quantity_used=body.quantity_used,
        notes=body.notes,
    )
    await db.commit()
    await db.refresh(event)
    return event


@router.post("/{event_id}/reverse", response_model=UsageEventOut, status_code=201)
async def reverse_usage_event(
    event_id: int,
    body: UsageEventReverseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Reverse a usage event, restoring the consumed quantity.
    Creates a compensating reversal record; original is preserved for audit.
    Requires can_manage_inventory permission.
    """
    from app.core.permissions import require_manage_inventory
    require_manage_inventory(current_user)

    reversal = await reverse_usage(
        db,
        event_id=event_id,
        reversed_by_user_id=current_user.id,
        notes=body.notes,
    )
    await db.commit()
    await db.refresh(reversal)
    return reversal


@router.get("/item/{item_id}", response_model=List[UsageEventOut])
async def list_usage_events_for_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(UsageEvent)
        .where(UsageEvent.item_id == item_id)
        .order_by(UsageEvent.used_at.desc())
        .limit(100)
    )
    return result.scalars().all()
