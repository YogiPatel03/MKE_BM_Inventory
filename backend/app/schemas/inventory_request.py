from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InventoryRequestCreate(BaseModel):
    item_id: Optional[int] = None
    bin_id: Optional[int] = None
    quantity_requested: int = Field(default=1, ge=1)
    reason: Optional[str] = None
    due_at: Optional[datetime] = None

    @model_validator(mode="after")
    def require_item_or_bin(self) -> "InventoryRequestCreate":
        if not self.item_id and not self.bin_id:
            raise ValueError("Either item_id or bin_id must be provided")
        if self.item_id and self.bin_id:
            raise ValueError("Provide either item_id or bin_id, not both")
        return self


class InventoryRequestApprove(BaseModel):
    due_at: Optional[datetime] = None


class InventoryRequestDeny(BaseModel):
    denial_reason: Optional[str] = None


class InventoryRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    requester_id: int
    approver_id: Optional[int] = None
    item_id: Optional[int] = None
    bin_id: Optional[int] = None
    quantity_requested: int
    status: str
    reason: Optional[str] = None
    denial_reason: Optional[str] = None
    due_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    fulfilled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
