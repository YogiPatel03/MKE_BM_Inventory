from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ItemPurchaseSummary(BaseModel):
    """How much was purchased (restocking cost)."""
    item_id: int
    item_name: str
    cabinet_id: int
    total_purchased: int
    total_purchase_cost: Optional[float] = None


class ItemUsageSummary(BaseModel):
    """How much was consumed + inferred cost from historical purchase price."""
    item_id: int
    item_name: str
    cabinet_id: int
    total_used: int
    total_cost: Optional[float] = None
    unit: Optional[str] = None  # e.g. "ft", "sheet" — reserved for future


class ExpenseReport(BaseModel):
    period_start: datetime
    period_end: datetime
    total_purchase_spend: float
    total_usage_cost: float
    by_purchase: List[ItemPurchaseSummary]  # restocking view
    by_usage: List[ItemUsageSummary]       # consumption view

    # Legacy alias so existing frontend field still works
    @property
    def total_spend(self) -> float:
        return self.total_purchase_spend

    @property
    def by_item(self) -> List[ItemUsageSummary]:
        return self.by_usage


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
