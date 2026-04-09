"""
QR code router — generate tokens and resolve scanned tokens.

GET /qr/resolve?token=<uuid>  → returns { type: "item"|"bin", id: int }
POST /qr/item/{item_id}/generate  → generates/regenerates QR token for item
POST /qr/bin/{bin_id}/generate    → generates/regenerates QR token for bin
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user as get_current_active_user, get_db
from app.core.permissions import require_manage_inventory
from app.models.bin import Bin
from app.models.item import Item
from app.models.user import User
router = APIRouter(prefix="/qr", tags=["qr"])


class QRResolveOut(BaseModel):
    type: str  # "item" or "bin"
    id: int


class QRTokenOut(BaseModel):
    token: str


@router.get("/resolve", response_model=QRResolveOut)
async def resolve_token(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    # Try item first
    item_result = await db.execute(select(Item).where(Item.qr_code_token == token))
    item = item_result.scalar_one_or_none()
    if item:
        return QRResolveOut(type="item", id=item.id)

    bin_result = await db.execute(select(Bin).where(Bin.qr_code_token == token))
    bin_obj = bin_result.scalar_one_or_none()
    if bin_obj:
        return QRResolveOut(type="bin", id=bin_obj.id)

    raise HTTPException(status.HTTP_404_NOT_FOUND, "QR token not found")


@router.post("/item/{item_id}/generate", response_model=QRTokenOut)
async def generate_item_qr(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manage_inventory(current_user)
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")

    token = item.generate_qr_token()
    await db.commit()
    return QRTokenOut(token=token)


@router.post("/bin/{bin_id}/generate", response_model=QRTokenOut)
async def generate_bin_qr(
    bin_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manage_inventory(current_user)
    result = await db.execute(select(Bin).where(Bin.id == bin_id))
    bin_obj = result.scalar_one_or_none()
    if not bin_obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bin not found")

    token = bin_obj.generate_qr_token()
    await db.commit()
    return QRTokenOut(token=token)
