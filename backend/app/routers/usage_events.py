from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user as get_current_active_user, get_db
from app.models.user import User
from app.schemas.usage_event import UsageEventCreate, UsageEventOut
from app.services.usage_service import mark_as_used

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
