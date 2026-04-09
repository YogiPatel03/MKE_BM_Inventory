from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user as get_current_active_user, get_db
from app.core.permissions import require_manage_inventory
from app.models.stock_adjustment import StockAdjustment
from app.models.user import User
from app.schemas.stock_adjustment import StockAdjustmentCreate, StockAdjustmentOut
from app.services.stock_service import adjust_stock

router = APIRouter(prefix="/stock-adjustments", tags=["stock-adjustments"])


@router.post("", response_model=StockAdjustmentOut, status_code=201)
async def create_adjustment(
    body: StockAdjustmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manage_inventory(current_user)
    adj = await adjust_stock(
        db,
        item_id=body.item_id,
        adjusted_by_user_id=current_user.id,
        delta=body.delta,
        reason=body.reason,
        notes=body.notes,
    )
    await db.commit()
    await db.refresh(adj)
    return adj


@router.get("/item/{item_id}", response_model=List[StockAdjustmentOut])
async def list_adjustments_for_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manage_inventory(current_user)
    result = await db.execute(
        select(StockAdjustment)
        .where(StockAdjustment.item_id == item_id)
        .order_by(StockAdjustment.adjusted_at.desc())
    )
    return result.scalars().all()
