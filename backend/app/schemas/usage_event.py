from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UsageEventCreate(BaseModel):
    item_id: int
    quantity_used: Decimal = Field(default=Decimal("1"), gt=Decimal("0"), decimal_places=2)
    notes: Optional[str] = None


class UsageEventReverseRequest(BaseModel):
    notes: Optional[str] = None


class UsageEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    user_id: int
    processed_by_user_id: Optional[int] = None
    quantity_used: Decimal
    notes: Optional[str] = None
    is_reversal: bool = False
    reverses_event_id: Optional[int] = None
    used_at: datetime
    created_at: datetime
