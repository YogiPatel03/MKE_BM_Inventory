"""
Move service — relocate items or bins, recording an audit trail.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.bin import Bin
from app.models.item import Item  # noqa: F401 — used in both move_item and cascade
from app.models.location_change_log import LocationChangeLog

log = logging.getLogger(__name__)


async def move_item(
    db: AsyncSession,
    *,
    item_id: int,
    moved_by_user_id: int,
    to_cabinet_id: int,
    to_bin_id: int | None,
    notes: str | None,
) -> LocationChangeLog:
    result = await db.execute(
        select(Item).where(Item.id == item_id, Item.is_active == True).with_for_update()
    )
    item = result.scalar_one_or_none()
    if not item:
        raise NotFoundError("Item", item_id)

    log_entry = LocationChangeLog(
        entity_type="item",
        entity_id=item_id,
        moved_by_user_id=moved_by_user_id,
        from_cabinet_id=item.cabinet_id,
        to_cabinet_id=to_cabinet_id,
        from_bin_id=item.bin_id,
        to_bin_id=to_bin_id,
        notes=notes,
    )
    db.add(log_entry)

    item.cabinet_id = to_cabinet_id
    item.bin_id = to_bin_id

    await db.flush()
    await db.refresh(log_entry)
    log.info("MoveItem: item=%d %s->%s", item_id, log_entry.from_cabinet_id, to_cabinet_id)
    return log_entry


async def move_bin(
    db: AsyncSession,
    *,
    bin_id: int,
    moved_by_user_id: int,
    to_cabinet_id: int,
    notes: str | None,
) -> LocationChangeLog:
    result = await db.execute(
        select(Bin).where(Bin.id == bin_id).with_for_update()
    )
    bin_obj = result.scalar_one_or_none()
    if not bin_obj:
        raise NotFoundError("Bin", bin_id)

    log_entry = LocationChangeLog(
        entity_type="bin",
        entity_id=bin_id,
        moved_by_user_id=moved_by_user_id,
        from_cabinet_id=bin_obj.cabinet_id,
        to_cabinet_id=to_cabinet_id,
        notes=notes,
    )
    db.add(log_entry)

    bin_obj.cabinet_id = to_cabinet_id

    # Cascade cabinet change to all items inside the bin so location stays consistent
    items_result = await db.execute(select(Item).where(Item.bin_id == bin_id))
    for item in items_result.scalars().all():
        item.cabinet_id = to_cabinet_id

    await db.flush()
    await db.refresh(log_entry)
    log.info(
        "MoveBin: bin=%d %s->%s (cascaded to contained items)",
        bin_id,
        log_entry.from_cabinet_id,
        to_cabinet_id,
    )
    return log_entry
