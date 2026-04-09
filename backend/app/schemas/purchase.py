from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PurchaseRecordCreate(BaseModel):
    item_id: int
    quantity_purchased: int = Field(..., ge=1)
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    vendor: Optional[str] = None
    notes: Optional[str] = None
    receipt_id: Optional[int] = None


class PurchaseRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    purchased_by_user_id: int
    receipt_id: Optional[int] = None
    quantity_purchased: int
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    vendor: Optional[str] = None
    notes: Optional[str] = None
    purchased_at: datetime
    created_at: datetime


class ReceiptRecordCreate(BaseModel):
    total_amount: Optional[float] = None
    vendor: Optional[str] = None
    notes: Optional[str] = None


class ReceiptRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uploaded_by_user_id: Optional[int] = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    total_amount: Optional[float] = None
    vendor: Optional[str] = None
    notes: Optional[str] = None
    uploaded_via: str
    uploaded_at: datetime
    created_at: datetime
