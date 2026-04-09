"""
Usage service — consumable item "mark as used" logic.

Consumable items decrement quantity_total permanently (they're consumed,
not returned). UsageEvent is the audit trail; Transaction is NOT used.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InsufficientStockError, NotFoundError, TransactionConflictError
from app.models.activity_log import ActivityType
from app.models.item import Item
from app.models.usage_event import UsageEvent
from app.services.activity_service import log_activity
from app.services.restock_service import move_to_restock_if_zero, restore_from_restock_if_nonzero
from app.services import telegram_service

log = logging.getLogger(__name__)


def _effective_threshold(item: Item) -> int:
    """Returns the low-stock threshold for an item."""
    if item.low_stock_threshold is not None:
        return item.low_stock_threshold
    return max(1, item.quantity_total // 10)


def _is_low_stock(item: Item) -> bool:
    threshold = _effective_threshold(item)
    return 0 < item.quantity_available <= threshold


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

    qty_before = item.quantity_available
    threshold = _effective_threshold(item)

    # Consumables are permanently consumed
    item.quantity_available -= quantity_used
    item.quantity_total -= quantity_used

    event = UsageEvent(
        item_id=item_id,
        user_id=user_id,
        processed_by_user_id=processed_by_user_id,
        quantity_used=quantity_used,
        notes=notes,
        is_reversal=False,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)

    cost_impact = None
    if item.unit_price:
        cost_impact = float(item.unit_price) * quantity_used

    await log_activity(
        db,
        activity_type=ActivityType.USAGE_RECORDED,
        actor_id=processed_by_user_id,
        target_item_id=item_id,
        target_cabinet_id=item.cabinet_id,
        quantity_delta=-quantity_used,
        cost_impact=cost_impact,
        notes=notes,
        metadata={"quantity_before": qty_before, "quantity_after": item.quantity_available},
        source_type="usage_event",
        source_id=event.id,
    )

    # Restock Me auto-move if now at zero
    await move_to_restock_if_zero(db, item, actor_id=processed_by_user_id)

    # Telegram threshold alerts (only on downward crossing)
    item_name = item.name
    qty_after = item.quantity_available

    log.info(
        "UsageEvent: event=%d item=%d user=%d qty=%d",
        event.id, item_id, user_id, quantity_used,
    )

    # Fire alerts after flush so we have all data; actual sends happen async
    if qty_after == 0 and qty_before > 0:
        location = f"Cabinet {item.cabinet_id}" + (f" / Bin {item.bin_id}" if item.bin_id else "")
        await telegram_service.notify_out_of_stock(item_name, location)
    elif qty_before > threshold and qty_after <= threshold and qty_after > 0:
        location = f"Cabinet {item.cabinet_id}" + (f" / Bin {item.bin_id}" if item.bin_id else "")
        await telegram_service.notify_low_stock(item_name, qty_after, threshold, location)

    return event


async def reverse_usage(
    db: AsyncSession,
    *,
    event_id: int,
    reversed_by_user_id: int,
    notes: str | None,
) -> UsageEvent:
    """
    Reverse a prior usage event by creating a compensating UsageEvent.

    The original event is NOT modified (audit trail preserved). The reversal
    event restores quantity_available and quantity_total, and may trigger
    Restock Me restoration if stock goes from 0 to >0.
    """
    result = await db.execute(
        select(UsageEvent).where(UsageEvent.id == event_id)
    )
    original = result.scalar_one_or_none()
    if not original:
        raise NotFoundError("UsageEvent", event_id)

    if original.is_reversal:
        raise TransactionConflictError("Cannot reverse a reversal event.")

    # Check if already reversed
    existing_result = await db.execute(
        select(UsageEvent).where(UsageEvent.reverses_event_id == event_id)
    )
    if existing_result.scalar_one_or_none():
        raise TransactionConflictError(f"UsageEvent {event_id} has already been reversed.")

    item_result = await db.execute(
        select(Item).where(Item.id == original.item_id, Item.is_active == True).with_for_update()
    )
    item = item_result.scalar_one_or_none()
    if not item:
        raise NotFoundError("Item", original.item_id)

    qty_before = item.quantity_available
    threshold = _effective_threshold(item)

    item.quantity_available += original.quantity_used
    item.quantity_total += original.quantity_used

    reversal = UsageEvent(
        item_id=original.item_id,
        user_id=original.user_id,
        processed_by_user_id=reversed_by_user_id,
        quantity_used=original.quantity_used,
        notes=f"Reversal of event #{original.id}" + (f": {notes}" if notes else ""),
        is_reversal=True,
        reverses_event_id=original.id,
    )
    db.add(reversal)
    await db.flush()
    await db.refresh(reversal)

    cost_impact = None
    if item.unit_price:
        cost_impact = float(item.unit_price) * original.quantity_used

    await log_activity(
        db,
        activity_type=ActivityType.USAGE_REVERSED,
        actor_id=reversed_by_user_id,
        target_item_id=original.item_id,
        target_cabinet_id=item.cabinet_id,
        quantity_delta=+original.quantity_used,
        cost_impact=-cost_impact if cost_impact else None,
        notes=reversal.notes,
        metadata={
            "original_event_id": original.id,
            "quantity_restored": original.quantity_used,
            "quantity_before": qty_before,
            "quantity_after": item.quantity_available,
        },
        source_type="usage_event",
        source_id=reversal.id,
    )

    # Restore from Restock Me if stock went from 0 to >0
    await restore_from_restock_if_nonzero(db, item, actor_id=reversed_by_user_id)

    log.info(
        "UsageReversal: reversal=%d original=%d item=%d qty_restored=%d",
        reversal.id, original.id, original.item_id, original.quantity_used,
    )
    return reversal
