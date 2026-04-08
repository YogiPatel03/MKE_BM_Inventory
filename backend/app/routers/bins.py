from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_manage_bins
from app.dependencies import get_current_user, get_db
from app.models.bin import Bin
from app.models.cabinet import Cabinet
from app.models.user import User
from app.schemas.bin import BinCreate, BinOut, BinUpdate

router = APIRouter(prefix="/bins", tags=["bins"])


@router.get("", response_model=list[BinOut])
async def list_bins(
    cabinet_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Bin]:
    query = select(Bin).order_by(Bin.label)
    if cabinet_id:
        query = query.where(Bin.cabinet_id == cabinet_id)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("", response_model=BinOut, status_code=status.HTTP_201_CREATED)
async def create_bin(
    body: BinCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Bin:
    require_manage_bins(current_user)

    cabinet_result = await db.execute(select(Cabinet).where(Cabinet.id == body.cabinet_id))
    if not cabinet_result.scalar_one_or_none():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cabinet not found")

    bin_ = Bin(**body.model_dump())
    db.add(bin_)
    await db.commit()
    await db.refresh(bin_)
    return bin_


@router.get("/{bin_id}", response_model=BinOut)
async def get_bin(
    bin_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Bin:
    result = await db.execute(select(Bin).where(Bin.id == bin_id))
    bin_ = result.scalar_one_or_none()
    if not bin_:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bin not found")
    return bin_


@router.patch("/{bin_id}", response_model=BinOut)
async def update_bin(
    bin_id: int,
    body: BinUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Bin:
    require_manage_bins(current_user)
    result = await db.execute(select(Bin).where(Bin.id == bin_id))
    bin_ = result.scalar_one_or_none()
    if not bin_:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bin not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(bin_, field, value)

    await db.commit()
    await db.refresh(bin_)
    return bin_


@router.delete("/{bin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bin(
    bin_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    require_manage_bins(current_user)
    result = await db.execute(select(Bin).where(Bin.id == bin_id))
    bin_ = result.scalar_one_or_none()
    if not bin_:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bin not found")
    await db.delete(bin_)
    await db.commit()
