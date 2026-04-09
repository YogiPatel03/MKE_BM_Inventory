from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_manage_cabinets
from app.dependencies import get_current_user, get_db
from app.models.activity_log import ActivityType
from app.models.cabinet import Cabinet
from app.models.user import User
from app.schemas.cabinet import CabinetCreate, CabinetDetail, CabinetOut, CabinetUpdate
from app.services.activity_service import log_activity
from app.services.inventory_service import get_cabinet_detail

router = APIRouter(prefix="/cabinets", tags=["cabinets"])


@router.get("", response_model=list[CabinetOut])
async def list_cabinets(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Cabinet]:
    result = await db.execute(select(Cabinet).order_by(Cabinet.name))
    return list(result.scalars().all())


@router.post("", response_model=CabinetOut, status_code=status.HTTP_201_CREATED)
async def create_cabinet(
    body: CabinetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Cabinet:
    require_manage_cabinets(current_user)
    cabinet = Cabinet(**body.model_dump())
    db.add(cabinet)
    await db.commit()
    await db.refresh(cabinet)
    return cabinet


@router.get("/{cabinet_id}", response_model=CabinetDetail)
async def get_cabinet(
    cabinet_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CabinetDetail:
    detail = await get_cabinet_detail(db, cabinet_id)
    if not detail:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cabinet not found")
    return detail


@router.patch("/{cabinet_id}", response_model=CabinetOut)
async def update_cabinet(
    cabinet_id: int,
    body: CabinetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Cabinet:
    require_manage_cabinets(current_user)
    result = await db.execute(select(Cabinet).where(Cabinet.id == cabinet_id))
    cabinet = result.scalar_one_or_none()
    if not cabinet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cabinet not found")

    changes = body.model_dump(exclude_none=True)
    before = {k: getattr(cabinet, k) for k in changes}
    for field, value in changes.items():
        setattr(cabinet, field, value)
    after = {k: getattr(cabinet, k) for k in changes}

    await log_activity(
        db,
        activity_type=ActivityType.CABINET_EDITED,
        actor_id=current_user.id,
        target_cabinet_id=cabinet.id,
        metadata={"before": before, "after": after},
        source_type="cabinet",
        source_id=cabinet.id,
    )

    await db.commit()
    await db.refresh(cabinet)
    return cabinet


@router.delete("/{cabinet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cabinet(
    cabinet_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    require_manage_cabinets(current_user)
    result = await db.execute(select(Cabinet).where(Cabinet.id == cabinet_id))
    cabinet = result.scalar_one_or_none()
    if not cabinet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cabinet not found")
    await db.delete(cabinet)
    await db.commit()
