"""
Reports router — inventory status and expense/usage summaries.
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user as get_current_active_user, get_db
from app.core.permissions import require_manage_inventory
from app.models.item import Item
from app.models.purchase_record import PurchaseRecord
from app.models.transaction import Transaction, TransactionStatus
from app.models.usage_event import UsageEvent
from app.models.user import User
from app.schemas.report import (
    ExpenseReport,
    InventoryStatusReport,
    ItemPurchaseSummary,
    ItemUsageSummary,
    LowStockItem,
)

router = APIRouter(prefix="/reports", tags=["reports"])

LOW_STOCK_THRESHOLD = 2


@router.get("/inventory-status", response_model=InventoryStatusReport)
async def inventory_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manage_inventory(current_user)

    total_result = await db.execute(
        select(func.count()).select_from(Item).where(Item.is_active == True)
    )
    total_items = total_result.scalar_one()

    low_stock_result = await db.execute(
        select(Item).where(
            Item.is_active == True,
            Item.quantity_available <= LOW_STOCK_THRESHOLD,
        )
    )
    low_stock_items = [
        LowStockItem(
            item_id=i.id,
            item_name=i.name,
            cabinet_id=i.cabinet_id,
            bin_id=i.bin_id,
            quantity_available=i.quantity_available,
            quantity_total=i.quantity_total,
        )
        for i in low_stock_result.scalars().all()
    ]

    checked_out_result = await db.execute(
        select(func.count()).select_from(Transaction).where(
            Transaction.status == TransactionStatus.CHECKED_OUT
        )
    )
    overdue_result = await db.execute(
        select(func.count()).select_from(Transaction).where(
            Transaction.status == TransactionStatus.OVERDUE
        )
    )

    return InventoryStatusReport(
        total_items=total_items,
        low_stock_items=low_stock_items,
        checked_out_count=checked_out_result.scalar_one(),
        overdue_count=overdue_result.scalar_one(),
    )


@router.get("/expenses", response_model=ExpenseReport)
async def expense_report(
    start: Optional[datetime] = Query(None, description="Period start (ISO 8601)"),
    end: Optional[datetime] = Query(None, description="Period end (ISO 8601)"),
    item_id: Optional[int] = Query(None, description="Filter to a specific item"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manage_inventory(current_user)

    now = datetime.now(timezone.utc)
    period_start = start or datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    period_end = end or now

    # ── Purchase (restocking) side ──────────────────────────────────────────
    purchase_query = (
        select(PurchaseRecord, Item)
        .join(Item, PurchaseRecord.item_id == Item.id)
        .where(PurchaseRecord.purchased_at.between(period_start, period_end))
    )
    if item_id:
        purchase_query = purchase_query.where(PurchaseRecord.item_id == item_id)

    purchase_rows = (await db.execute(purchase_query)).all()

    by_purchase: dict[int, ItemPurchaseSummary] = {}
    total_purchase_spend = 0.0

    for purchase, item in purchase_rows:
        cost = float(purchase.total_price or 0)
        total_purchase_spend += cost
        if item.id not in by_purchase:
            by_purchase[item.id] = ItemPurchaseSummary(
                item_id=item.id,
                item_name=item.name,
                cabinet_id=item.cabinet_id,
                total_purchased=0,
                total_purchase_cost=0.0,
            )
        by_purchase[item.id].total_purchased += purchase.quantity_purchased
        by_purchase[item.id].total_purchase_cost = (
            (by_purchase[item.id].total_purchase_cost or 0.0) + cost
        )

    # ── Usage (consumption) side ────────────────────────────────────────────
    # For each usage event, derive cost from the most recent purchase price at or before that event.
    usage_query = (
        select(UsageEvent, Item)
        .join(Item, UsageEvent.item_id == Item.id)
        .where(UsageEvent.used_at.between(period_start, period_end))
    )
    if item_id:
        usage_query = usage_query.where(UsageEvent.item_id == item_id)

    usage_rows = (await db.execute(usage_query)).all()

    by_usage: dict[int, ItemUsageSummary] = {}
    total_usage_cost = 0.0

    for usage_event, item in usage_rows:
        # Find the most recent purchase for this item at or before the usage event
        price_result = await db.execute(
            select(PurchaseRecord.unit_price)
            .where(
                PurchaseRecord.item_id == item.id,
                PurchaseRecord.purchased_at <= usage_event.used_at,
                PurchaseRecord.unit_price.is_not(None),
            )
            .order_by(PurchaseRecord.purchased_at.desc())
            .limit(1)
        )
        historical_price = price_result.scalar_one_or_none()
        # Fall back to item's current unit_price if no purchase record exists
        unit_cost = float(historical_price or item.unit_price or 0)
        event_cost = unit_cost * usage_event.quantity_used
        total_usage_cost += event_cost

        if item.id not in by_usage:
            by_usage[item.id] = ItemUsageSummary(
                item_id=item.id,
                item_name=item.name,
                cabinet_id=item.cabinet_id,
                total_used=0,
                total_cost=0.0,
            )
        by_usage[item.id].total_used += usage_event.quantity_used
        by_usage[item.id].total_cost = (by_usage[item.id].total_cost or 0.0) + event_cost

    return ExpenseReport(
        period_start=period_start,
        period_end=period_end,
        total_purchase_spend=total_purchase_spend,
        total_usage_cost=total_usage_cost,
        by_purchase=list(by_purchase.values()),
        by_usage=list(by_usage.values()),
    )
