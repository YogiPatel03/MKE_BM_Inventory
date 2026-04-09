"""
Usage service — consumable item "mark as used" logic.

Consumable items decrement quantity_total permanently (they're consumed,
not returned). UsageEvent is the audit trail; Transaction is NOT used.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InsufficientStockError, NotFoundError, TransactionConflictError
from app.models.item import Item
from app.models.usage_event import UsageEvent

log = logging.getLogger(__name__)


async def mark_as_used(
    db: AsyncSession,
    *,
    item_id: int,
    user_id: int,
    processed_by_user_id: int,
    quantity_used: int,
    notes: str | None,
) -> UsageEvent:
    result = await db.execute(
        select(Item).where(Item.id == item_id, Item.is_active == True).with_for_update()
    )
    item = result.scalar_one_or_none()
    if not item:
        raise NotFoundError("Item", item_id)

    if not item.is_consumable:
        raise TransactionConflictError(
            f"Item '{item.name}' is not consumable. Use checkout/return instead."
        )

    if item.quantity_available < quantity_used:
        raise InsufficientStockError(item.name, quantity_used, item.quantity_available)

    # Consumables are permanently consumed
    item.quantity_available -= quantity_used
    item.quantity_total -= quantity_used

    event = UsageEvent(
        item_id=item_id,
        user_id=user_id,
        processed_by_user_id=processed_by_user_id,
        quantity_used=quantity_used,
        notes=notes,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)

    log.info(
        "UsageEvent: event=%d item=%d user=%d qty=%d",
        event.id,
        item_id,
        user_id,
        quantity_used,
    )
    return event
