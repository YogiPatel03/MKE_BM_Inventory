"""
Stock adjustment service — auditable manual inventory count corrections.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, TransactionConflictError
from app.models.activity_log import ActivityType
from app.models.item import Item
from app.models.stock_adjustment import StockAdjustment
from app.services.activity_service import log_activity
from app.services.restock_service import move_to_restock_if_zero, restore_from_restock_if_nonzero
from app.services import telegram_service

log = logging.getLogger(__name__)


def _effective_threshold(item: Item) -> int:
    if item.low_stock_threshold is not None:
        return item.low_stock_threshold
    return max(1, item.quantity_total // 10)


async def adjust_stock(
    db: AsyncSession,
    *,
    item_id: int,
    adjusted_by_user_id: int,
    delta: int,
    reason: str,
    notes: str | None,
) -> StockAdjustment:
    """
    Adjust item.quantity_total and quantity_available by delta.
    Both go up or down together (this represents adding/removing physical stock,
    not a checkout). Cannot reduce below 0.
    """
    result = await db.execute(
        select(Item).where(Item.id == item_id, Item.is_active == True).with_for_update()
    )
    item = result.scalar_one_or_none()
    if not item:
        raise NotFoundError("Item", item_id)

    new_total = item.quantity_total + delta
    new_available = item.quantity_available + delta

    if new_total < 0:
        raise TransactionConflictError(
            f"Adjustment would set quantity_total to {new_total}. "
            f"Reduce delta to at most {item.quantity_total}."
        )
    if new_available < 0:
        raise TransactionConflictError(
            f"Adjustment would set quantity_available to {new_available}. "
            f"{abs(new_available)} units are currently checked out."
        )

    qty_before = item.quantity_total
    threshold_before = _effective_threshold(item)
    available_before = item.quantity_available

    item.quantity_total = new_total
    item.quantity_available = new_available

    adjustment = StockAdjustment(
        item_id=item_id,
        adjusted_by_user_id=adjusted_by_user_id,
        delta=delta,
        quantity_before=qty_before,
        quantity_after=new_total,
        reason=reason,
        notes=notes,
    )
    db.add(adjustment)
    await db.flush()
    await db.refresh(adjustment)

    activity_type = ActivityType.STOCK_ADJUSTMENT_INCREASE if delta > 0 else ActivityType.STOCK_ADJUSTMENT_DECREASE
    await log_activity(
        db,
        activity_type=activity_type,
        actor_id=adjusted_by_user_id,
        target_item_id=item_id,
        target_cabinet_id=item.cabinet_id,
        quantity_delta=delta,
        notes=notes,
        metadata={"reason": reason, "quantity_before": qty_before, "quantity_after": new_total},
        source_type="stock_adjustment",
        source_id=adjustment.id,
    )

    # Restock Me auto-move / restore
    if new_available == 0 and available_before > 0:
        await move_to_restock_if_zero(db, item, actor_id=adjusted_by_user_id)
    elif new_available > 0 and available_before == 0:
        await restore_from_restock_if_nonzero(db, item, actor_id=adjusted_by_user_id)

    # Telegram threshold alerts
    threshold_after = _effective_threshold(item)
    item_name = item.name
    if new_available == 0 and available_before > 0:
        location = f"Cabinet {item.cabinet_id}" + (f" / Bin {item.bin_id}" if item.bin_id else "")
        await telegram_service.notify_out_of_stock(item_name, location)
    elif available_before > threshold_before and new_available <= threshold_after and new_available > 0:
        location = f"Cabinet {item.cabinet_id}" + (f" / Bin {item.bin_id}" if item.bin_id else "")
        await telegram_service.notify_low_stock(item_name, new_available, threshold_after, location)

    log.info(
        "StockAdjustment: adj=%d item=%d delta=%+d by=%d",
        adjustment.id, item_id, delta, adjusted_by_user_id,
    )
    return adjustment
