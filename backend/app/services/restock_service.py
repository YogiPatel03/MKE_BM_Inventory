"""
Restock Me service — automatic movement of zero-stock consumables.

When a consumable item's quantity_available hits 0:
  1. The item is moved into the "Restock Me" cabinet.
  2. Its prior location (cabinet_id, bin_id) is saved on the item.
  3. An ActivityLog entry is created.

When stock is restored to > 0:
  1. The item is moved back to its saved prior location.
  2. Prior location fields are cleared.
  3. An ActivityLog entry is created.

The "Restock Me" cabinet is created idempotently on startup.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityType
from app.models.cabinet import Cabinet
from app.models.item import Item
from app.services.activity_service import log_activity

log = logging.getLogger(__name__)

RESTOCK_CABINET_NAME = "Restock Me"


async def get_or_create_restock_cabinet(db: AsyncSession) -> Cabinet:
    """Idempotent: returns existing 'Restock Me' cabinet or creates it."""
    result = await db.execute(
        select(Cabinet).where(Cabinet.name == RESTOCK_CABINET_NAME)
    )
    cabinet = result.scalar_one_or_none()
    if cabinet:
        return cabinet

    cabinet = Cabinet(
        name=RESTOCK_CABINET_NAME,
        location="Auto-managed",
        description="Items placed here automatically when stock reaches zero. Return to original location after restocking.",
    )
    db.add(cabinet)
    await db.flush()
    await db.refresh(cabinet)
    log.info("Created 'Restock Me' cabinet id=%d", cabinet.id)
    return cabinet


async def move_to_restock_if_zero(
    db: AsyncSession,
    item: Item,
    actor_id: int | None = None,
) -> bool:
    """
    If item.quantity_available == 0 and it is not already in Restock Me,
    move it there and save prior location. Returns True if moved.

    Must be called inside an open transaction.
    """
    if item.quantity_available != 0:
        return False

    restock = await get_or_create_restock_cabinet(db)

    if item.cabinet_id == restock.id:
        return False  # already there

    # Save prior location so we can restore later
    item.prior_cabinet_id = item.cabinet_id
    item.prior_bin_id = item.bin_id

    item.cabinet_id = restock.id
    item.bin_id = None

    await log_activity(
        db,
        activity_type=ActivityType.ITEM_MOVED_TO_RESTOCK,
        actor_id=actor_id,
        target_item_id=item.id,
        target_cabinet_id=restock.id,
        notes=f"Auto-moved to Restock Me (zero stock). Prior location: cabinet {item.prior_cabinet_id}, bin {item.prior_bin_id}",
        metadata={
            "prior_cabinet_id": item.prior_cabinet_id,
            "prior_bin_id": item.prior_bin_id,
            "restock_cabinet_id": restock.id,
        },
        source_type="item",
        source_id=item.id,
    )
    log.info("Item %d moved to Restock Me (zero stock)", item.id)
    return True


async def restore_from_restock_if_nonzero(
    db: AsyncSession,
    item: Item,
    actor_id: int | None = None,
) -> bool:
    """
    If item.quantity_available > 0 and it has a saved prior location,
    move it back. Returns True if restored.

    Must be called inside an open transaction.
    """
    if item.quantity_available <= 0:
        return False

    if item.prior_cabinet_id is None:
        return False  # no prior location saved — wasn't in Restock Me

    restock = await get_or_create_restock_cabinet(db)
    if item.cabinet_id != restock.id:
        # Not in Restock Me — prior_cabinet_id may be stale, clear it
        item.prior_cabinet_id = None
        item.prior_bin_id = None
        return False

    restore_cabinet_id = item.prior_cabinet_id
    restore_bin_id = item.prior_bin_id

    item.cabinet_id = restore_cabinet_id
    item.bin_id = restore_bin_id
    item.prior_cabinet_id = None
    item.prior_bin_id = None

    await log_activity(
        db,
        activity_type=ActivityType.ITEM_RESTORED_FROM_RESTOCK,
        actor_id=actor_id,
        target_item_id=item.id,
        target_cabinet_id=restore_cabinet_id,
        notes=f"Restored from Restock Me to cabinet {restore_cabinet_id}, bin {restore_bin_id}",
        metadata={
            "restored_to_cabinet_id": restore_cabinet_id,
            "restored_to_bin_id": restore_bin_id,
        },
        source_type="item",
        source_id=item.id,
    )
    log.info("Item %d restored from Restock Me to cabinet=%d bin=%s", item.id, restore_cabinet_id, restore_bin_id)
    return True
