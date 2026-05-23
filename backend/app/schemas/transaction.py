from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.transaction import CheckoutPurpose
from app.schemas.item import ItemOut
from app.schemas.user import UserOut


class CheckoutRequest(BaseModel):
    item_id: int
    user_id: int
    quantity: float = 1.0
    due_at: Optional[datetime] = None
    notes: Optional[str] = None
    purpose: CheckoutPurpose = CheckoutPurpose.GENERAL

    @field_validator("quantity")
    @classmethod
    def qty_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("quantity must be greater than 0")
        return round(v, 2)


class ReturnRequest(BaseModel):
    notes: Optional[str] = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    user_id: int
    processed_by_user_id: Optional[int]
    quantity: float
    status: str
    checked_out_at: datetime
    due_at: Optional[datetime]
    returned_at: Optional[datetime]
    purpose: CheckoutPurpose
    notes: Optional[str]
    photo_requested_via_telegram: bool
    created_at: datetime
    updated_at: datetime


class TransactionDetail(TransactionOut):
    """Transaction with full related object data."""

    item: ItemOut
    user: UserOut
    processed_by: Optional[UserOut]
