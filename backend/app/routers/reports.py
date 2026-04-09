"""
Reports router — inventory status and expense summaries.
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
from app.models.user import User
from app.schemas.report import (
    ExpenseReport,
    InventoryStatusReport,
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
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manage_inventory(current_user)

    now = datetime.now(timezone.utc)
    period_start = start or datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    period_end = end or now

    result = await db.execute(
        select(PurchaseRecord, Item)
        .join(Item, PurchaseRecord.item_id == Item.id)
        .where(PurchaseRecord.purchased_at.between(period_start, period_end))
    )
    rows = result.all()

    # Aggregate by item
    by_item: dict[int, ItemUsageSummary] = {}
    total_spend = 0.0

    for purchase, item in rows:
        cost = float(purchase.total_price or 0)
        total_spend += cost
        if item.id not in by_item:
            by_item[item.id] = ItemUsageSummary(
                item_id=item.id,
                item_name=item.name,
                cabinet_id=item.cabinet_id,
                total_used=0,
                total_cost=0.0,
            )
        by_item[item.id].total_used += purchase.quantity_purchased
        by_item[item.id].total_cost = (by_item[item.id].total_cost or 0) + cost

    return ExpenseReport(
        period_start=period_start,
        period_end=period_end,
        total_spend=total_spend,
        by_item=list(by_item.values()),
    )
