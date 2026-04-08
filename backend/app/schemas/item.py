from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, model_validator


class ItemBase(BaseModel):
    name: str
    description: Optional[str] = None
    quantity_total: int = 1
    cabinet_id: int
    bin_id: Optional[int] = None
    sku: Optional[str] = None
    condition: str = "GOOD"


class ItemCreate(ItemBase):
    @model_validator(mode="after")
    def qty_check(self) -> "ItemCreate":
        if self.quantity_total < 1:
            raise ValueError("quantity_total must be at least 1")
        return self


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    quantity_total: Optional[int] = None
    cabinet_id: Optional[int] = None
    bin_id: Optional[int] = None
    sku: Optional[str] = None
    condition: Optional[str] = None
    is_active: Optional[bool] = None


class ItemOut(ItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    quantity_available: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
