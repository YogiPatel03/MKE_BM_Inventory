"""
Inventory service — helpers for cabinet/bin/item management.
Routers call these; they handle complex queries like cabinet detail with counts.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bin import Bin
from app.models.cabinet import Cabinet
from app.models.item import Item
from app.schemas.cabinet import CabinetDetail, CabinetOut


async def get_cabinets_with_counts(
    db: AsyncSession,
    room_id: int | None = None,
) -> list[CabinetOut]:
    """
    Return all cabinets (optionally filtered by room) with bin_count and item_count.

    item_count includes:
      - items directly in the cabinet (bin_id IS NULL)
      - items inside bins within the cabinet (bin_id IS NOT NULL)
    Only active items are counted.
    """
    # Subquery: bin counts per cabinet
    bin_sq = (
        select(Bin.cabinet_id, func.count(Bin.id).label("bin_count"))
        .group_by(Bin.cabinet_id)
        .subquery()
    )
    # Subquery: active item counts per cabinet (includes items in bins)
    item_sq = (
        select(Item.cabinet_id, func.count(Item.id).label("item_count"))
        .where(Item.is_active == True)
        .group_by(Item.cabinet_id)
        .subquery()
    )

    query = (
        select(
            Cabinet,
            func.coalesce(bin_sq.c.bin_count, 0).label("bin_count"),
            func.coalesce(item_sq.c.item_count, 0).label("item_count"),
        )
        .outerjoin(bin_sq, bin_sq.c.cabinet_id == Cabinet.id)
        .outerjoin(item_sq, item_sq.c.cabinet_id == Cabinet.id)
        .order_by(Cabinet.name)
    )
    if room_id is not None:
        query = query.where(Cabinet.room_id == room_id)

    rows = (await db.execute(query)).all()

    return [
        CabinetOut(
            id=cabinet.id,
            name=cabinet.name,
            location=cabinet.location,
            description=cabinet.description,
            room_id=cabinet.room_id,
            created_at=cabinet.created_at,
            updated_at=cabinet.updated_at,
            bin_count=int(bin_count),
            item_count=int(item_count),
        )
        for cabinet, bin_count, item_count in rows
    ]


async def get_cabinet_detail(db: AsyncSession, cabinet_id: int) -> CabinetDetail | None:
    result = await db.execute(select(Cabinet).where(Cabinet.id == cabinet_id))
    cabinet = result.scalar_one_or_none()
    if not cabinet:
        return None

    bin_count_result = await db.execute(
        select(func.count()).where(Bin.cabinet_id == cabinet_id)
    )
    bin_count = bin_count_result.scalar() or 0

    # Count all active items in this cabinet (including items inside bins)
    item_count_result = await db.execute(
        select(func.count()).where(Item.cabinet_id == cabinet_id, Item.is_active == True)
    )
    item_count = item_count_result.scalar() or 0

    return CabinetDetail(
        id=cabinet.id,
        name=cabinet.name,
        location=cabinet.location,
        description=cabinet.description,
        room_id=cabinet.room_id,
        created_at=cabinet.created_at,
        updated_at=cabinet.updated_at,
        bin_count=bin_count,
        item_count=item_count,
    )
