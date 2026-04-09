from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ItemUsageSummary(BaseModel):
    item_id: int
    item_name: str
    cabinet_id: int
    total_used: int
    total_cost: Optional[float] = None


class ExpenseReport(BaseModel):
    period_start: datetime
    period_end: datetime
    total_spend: float
    by_item: List[ItemUsageSummary]


class LowStockItem(BaseModel):
    item_id: int
    item_name: str
    cabinet_id: int
    bin_id: Optional[int] = None
    quantity_available: int
    quantity_total: int


class InventoryStatusReport(BaseModel):
    total_items: int
    low_stock_items: List[LowStockItem]
    checked_out_count: int
    overdue_count: int
