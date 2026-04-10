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


class LowStockItem(BaseModel):
    item_id: int
    item_name: str
    cabinet_id: int
    bin_id: Optional[int] = None
    quantity_available: int
    quantity_total: int
    low_stock_threshold: Optional[int] = None


class OutOfStockItem(BaseModel):
    item_id: int
    item_name: str
    cabinet_id: int
    bin_id: Optional[int] = None


class InventoryStatusReport(BaseModel):
    total_items: int
    low_stock_items: List[LowStockItem]
    out_of_stock_items: List[OutOfStockItem]
    checked_out_count: int
    overdue_count: int


# ── Held-value report ─────────────────────────────────────────────────────────

class HeldValueItem(BaseModel):
    item_id: int
    item_name: str
    cabinet_id: int
    cabinet_name: str
    room_id: int
    room_name: str
    bin_id: Optional[int] = None
    quantity_total: int
    quantity_available: int
    unit_price: Optional[float] = None
    held_value: float  # unit_price * quantity_total


class HeldValueByCabinet(BaseModel):
    cabinet_id: int
    cabinet_name: str
    room_id: int
    room_name: str
    total_value: float
    item_count: int


class HeldValueByRoom(BaseModel):
    room_id: int
    room_name: str
    total_value: float
    cabinet_count: int
    item_count: int


class HeldValueReport(BaseModel):
    total_held_value: float
    total_items: int
    by_room: List[HeldValueByRoom]
    by_cabinet: List[HeldValueByCabinet]
    items: List[HeldValueItem]
