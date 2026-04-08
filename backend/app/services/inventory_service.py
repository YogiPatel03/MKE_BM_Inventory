"""
Inventory service — helpers for cabinet/bin/item management.
Routers call these; they handle complex queries like cabinet detail with counts.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bin import Bin
from app.models.cabinet import Cabinet
from app.models.item import Item
from app.schemas.cabinet import CabinetDetail


async def get_cabinet_detail(db: AsyncSession, cabinet_id: int) -> CabinetDetail | None:
    result = await db.execute(select(Cabinet).where(Cabinet.id == cabinet_id))
    cabinet = result.scalar_one_or_none()
    if not cabinet:
        return None

    bin_count_result = await db.execute(
        select(func.count()).where(Bin.cabinet_id == cabinet_id)
    )
    bin_count = bin_count_result.scalar() or 0

    item_count_result = await db.execute(
        select(func.count()).where(Item.cabinet_id == cabinet_id, Item.is_active == True)
    )
    item_count = item_count_result.scalar() or 0

    return CabinetDetail(
        id=cabinet.id,
        name=cabinet.name,
        location=cabinet.location,
        description=cabinet.description,
        created_at=cabinet.created_at,
        updated_at=cabinet.updated_at,
        bin_count=bin_count,
        item_count=item_count,
    )
