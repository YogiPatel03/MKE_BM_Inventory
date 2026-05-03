from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StockAdjustmentCreate(BaseModel):
    item_id: int
    delta: Decimal = Field(..., description="Signed quantity change: positive=add, negative=remove", decimal_places=2)
    reason: str = "CORRECTION"
    notes: Optional[str] = None


class StockAdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    adjusted_by_user_id: int
    delta: Decimal
    quantity_before: Decimal
    quantity_after: Decimal
    reason: str
    notes: Optional[str] = None
    adjusted_at: datetime
    created_at: datetime
