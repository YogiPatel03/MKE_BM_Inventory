from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class BinBase(BaseModel):
    label: str
    group_number: Optional[int] = None
    location_note: Optional[str] = None
    description: Optional[str] = None


class BinCreate(BinBase):
    cabinet_id: int


class BinUpdate(BaseModel):
    label: Optional[str] = None
    group_number: Optional[int] = None
    location_note: Optional[str] = None
    description: Optional[str] = None


class BinOut(BinBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cabinet_id: int
    qr_code_token: Optional[str] = None
    created_at: datetime
    updated_at: datetime
