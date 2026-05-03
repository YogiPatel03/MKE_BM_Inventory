from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class BinTransactionCreate(BaseModel):
    bin_id: int
    notes: Optional[str] = None
    due_at: Optional[datetime] = None


class BinTransactionReturn(BaseModel):
    notes: Optional[str] = None


class BinTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bin_id: int
    user_id: int
    processed_by_user_id: Optional[int] = None
    status: str
    checked_out_at: datetime
    due_at: Optional[datetime] = None
    returned_at: Optional[datetime] = None
    notes: Optional[str] = None
    included_item_ids: Optional[List[int]] = None
    created_at: datetime
    updated_at: datetime


class BinCheckoutOut(BinTransactionOut):
    """Checkout response that includes excluded items (already individually checked out)."""
    excluded_item_ids: List[int] = []
