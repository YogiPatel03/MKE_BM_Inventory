from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


def _normalize_sku(value: Optional[str]) -> Optional[str]:
    if value is None:
        return value
    stripped = value.strip()
    return stripped.upper() or None


class ItemBase(BaseModel):
    name: str
    description: Optional[str] = None
    quantity_total: float = 1
    cabinet_id: int
    bin_id: Optional[int] = None
    sku: Optional[str] = None
    condition: str = "GOOD"
    is_consumable: bool = False
    unit_price: Optional[float] = None
    low_stock_threshold: Optional[float] = None

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_sku(value)


class ItemCreate(ItemBase):
    sku: str

    @model_validator(mode="after")
    def qty_check(self) -> "ItemCreate":
        if self.quantity_total <= 0:
            raise ValueError("quantity_total must be greater than 0")
        if not self.sku:
            raise ValueError("sku is required")
        return self


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    quantity_total: Optional[float] = None
    cabinet_id: Optional[int] = None
    bin_id: Optional[int] = None
    sku: Optional[str] = None
    condition: Optional[str] = None
    is_active: Optional[bool] = None
    is_consumable: Optional[bool] = None
    unit_price: Optional[float] = None
    low_stock_threshold: Optional[float] = None

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_sku(value)


class ItemOut(ItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    quantity_available: float
    is_active: bool
    qr_code_token: Optional[str] = None
    low_stock_threshold: Optional[float] = None
    bin_label: Optional[str] = None
    bin_number: Optional[str] = None
    prior_cabinet_id: Optional[int] = None
    prior_bin_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
