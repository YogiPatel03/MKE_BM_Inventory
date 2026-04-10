from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class RoomBase(BaseModel):
    name: str
    description: Optional[str] = None


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class RoomOut(RoomBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class RoomDetail(RoomOut):
    """Room with cabinet count for dashboard display."""
    cabinet_count: int = 0
