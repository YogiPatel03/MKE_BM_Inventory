from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user as get_current_active_user, get_db
from app.core.permissions import require_manage_inventory
from app.models.user import User
from app.services.move_service import move_bin, move_item

router = APIRouter(prefix="/moves", tags=["moves"])


class MoveItemRequest(BaseModel):
    item_id: int
    to_cabinet_id: int
    to_bin_id: Optional[int] = None
    notes: Optional[str] = None


class MoveBinRequest(BaseModel):
    bin_id: int
    to_cabinet_id: int
    notes: Optional[str] = None


class MoveLogOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    from_cabinet_id: Optional[int] = None
    to_cabinet_id: Optional[int] = None
    from_bin_id: Optional[int] = None
    to_bin_id: Optional[int] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True


@router.post("/item", response_model=MoveLogOut, status_code=201)
async def move_item_endpoint(
    body: MoveItemRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manage_inventory(current_user)
    log_entry = await move_item(
        db,
        item_id=body.item_id,
        moved_by_user_id=current_user.id,
        to_cabinet_id=body.to_cabinet_id,
        to_bin_id=body.to_bin_id,
        notes=body.notes,
    )
    await db.commit()
    await db.refresh(log_entry)
    return log_entry


@router.post("/bin", response_model=MoveLogOut, status_code=201)
async def move_bin_endpoint(
    body: MoveBinRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manage_inventory(current_user)
    log_entry = await move_bin(
        db,
        bin_id=body.bin_id,
        moved_by_user_id=current_user.id,
        to_cabinet_id=body.to_cabinet_id,
        notes=body.notes,
    )
    await db.commit()
    await db.refresh(log_entry)
    return log_entry
