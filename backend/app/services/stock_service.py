"""
Stock adjustment service — auditable manual inventory count corrections.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, TransactionConflictError
from app.models.item import Item
from app.models.stock_adjustment import StockAdjustment

log = logging.getLogger(__name__)


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

    log.info(
        "StockAdjustment: adj=%d item=%d delta=%+d by=%d",
        adjustment.id,
        item_id,
        delta,
        adjusted_by_user_id,
    )
    return adjustment
