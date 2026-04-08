from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.item import ItemOut
from app.schemas.user import UserOut


class CheckoutRequest(BaseModel):
    item_id: int
    user_id: int
    quantity: int = 1
    due_at: Optional[datetime] = None
    notes: Optional[str] = None

    @field_validator("quantity")
    @classmethod
    def qty_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("quantity must be at least 1")
        return v


class ReturnRequest(BaseModel):
    notes: Optional[str] = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    user_id: int
    processed_by_user_id: Optional[int]
    quantity: int
    status: str
    checked_out_at: datetime
    due_at: Optional[datetime]
    returned_at: Optional[datetime]
    notes: Optional[str]
    photo_requested_via_telegram: bool
    created_at: datetime
    updated_at: datetime


class TransactionDetail(TransactionOut):
    """Transaction with full related object data."""

    item: ItemOut
    user: UserOut
    processed_by: Optional[UserOut]
