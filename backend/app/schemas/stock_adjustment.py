from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StockAdjustmentCreate(BaseModel):
    item_id: int
    delta: int = Field(..., description="Signed quantity change: positive=add, negative=remove")
    reason: str = "CORRECTION"
    notes: Optional[str] = None


class StockAdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    adjusted_by_user_id: int
    delta: int
    quantity_before: int
    quantity_after: int
    reason: str
    notes: Optional[str] = None
    adjusted_at: datetime
    created_at: datetime
