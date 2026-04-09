from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ActorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: str


class ItemRefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class BinRefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    label: str


class CabinetRefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class ActivityLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activity_type: str
    actor_id: Optional[int]
    actor: Optional[ActorOut]

    target_item_id: Optional[int]
    target_item: Optional[ItemRefOut]
    target_bin_id: Optional[int]
    target_bin: Optional[BinRefOut]
    target_cabinet_id: Optional[int]
    target_cabinet: Optional[CabinetRefOut]
    target_user_id: Optional[int]
    target_user: Optional[ActorOut]

    quantity_delta: Optional[int]
    cost_impact: Optional[float]
    notes: Optional[str]
    metadata_: Optional[dict[str, Any]]
    source_type: Optional[str]
    source_id: Optional[int]

    occurred_at: datetime
    created_at: datetime
