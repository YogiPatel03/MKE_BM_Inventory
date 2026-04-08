from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CabinetBase(BaseModel):
    name: str
    location: Optional[str] = None
    description: Optional[str] = None


class CabinetCreate(CabinetBase):
    pass


class CabinetUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None


class CabinetOut(CabinetBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class CabinetDetail(CabinetOut):
    """Cabinet with item and bin counts for dashboard display."""

    bin_count: int = 0
    item_count: int = 0
