from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CabinetBase(BaseModel):
    name: str
    location: Optional[str] = None
    description: Optional[str] = None
    room_id: int


class CabinetCreate(CabinetBase):
    pass


class CabinetUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    room_id: Optional[int] = None


class CabinetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: Optional[str] = None
    description: Optional[str] = None
    room_id: int
    created_at: datetime
    updated_at: datetime

    # Counts included in list responses (computed at query time)
    bin_count: int = 0
    item_count: int = 0


class CabinetDetail(CabinetOut):
    """Cabinet with item and bin counts for dashboard display."""
    pass
