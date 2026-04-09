"""
Activity router — unified inventory activity feed.

GET /api/activity         — paginated feed, newest first
GET /api/activity/types   — list all known activity type strings
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_current_user, get_db
from app.models.activity_log import ActivityLog
from app.models.user import User
from app.schemas.activity import ActivityLogOut

router = APIRouter(prefix="/activity", tags=["activity"])

KNOWN_TYPES = [
    "ITEM_CREATED",
    "ITEM_EDITED",
    "ITEM_DEACTIVATED",
    "ITEM_REACTIVATED",
    "CABINET_EDITED",
    "USER_EDITED",
    "USER_PASSWORD_RESET",
    "ITEM_CHECKED_OUT",
    "ITEM_RETURNED",
    "BIN_CHECKED_OUT",
    "BIN_RETURNED",
    "USAGE_RECORDED",
    "USAGE_REVERSED",
    "STOCK_ADJUSTMENT_INCREASE",
    "STOCK_ADJUSTMENT_DECREASE",
    "PURCHASE_LOGGED",
    "ITEM_MOVED",
    "BIN_MOVED",
    "ITEM_MOVED_TO_RESTOCK",
    "ITEM_RESTORED_FROM_RESTOCK",
    "REQUEST_FULFILLED",
]


@router.get("/types", response_model=list[str])
async def list_activity_types(_: User = Depends(get_current_user)) -> list[str]:
    return KNOWN_TYPES


@router.get("", response_model=list[ActivityLogOut])
async def list_activity(
    activity_type: Optional[str] = Query(None, description="Filter by activity type"),
    item_id: Optional[int] = Query(None),
    actor_id: Optional[int] = Query(None),
    since: Optional[datetime] = Query(None, description="Only events after this timestamp"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ActivityLog]:
    query = (
        select(ActivityLog)
        .options(
            selectinload(ActivityLog.actor),
            selectinload(ActivityLog.target_item),
            selectinload(ActivityLog.target_bin),
            selectinload(ActivityLog.target_cabinet),
            selectinload(ActivityLog.target_user),
        )
        .order_by(ActivityLog.occurred_at.desc())
    )

    if activity_type:
        query = query.where(ActivityLog.activity_type == activity_type)
    if item_id:
        query = query.where(ActivityLog.target_item_id == item_id)
    if actor_id:
        query = query.where(ActivityLog.actor_id == actor_id)
    if since:
        query = query.where(ActivityLog.occurred_at >= since)

    # Non-admin users can only see their own activity
    if not current_user.role.can_view_all_transactions:
        query = query.where(ActivityLog.actor_id == current_user.id)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())
