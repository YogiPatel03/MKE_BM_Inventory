from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


def _normalize_bin_number(value: Optional[str]) -> Optional[str]:
    if value is None:
        return value
    stripped = value.strip()
    if not stripped:
        raise ValueError("bin_number cannot be blank")
    return stripped.upper()


class BinBase(BaseModel):
    label: str
    bin_number: Optional[str] = None
    group_number: Optional[int] = None
    location_note: Optional[str] = None
    description: Optional[str] = None
    requires_full_bin_checkout: bool = False

    @field_validator("bin_number")
    @classmethod
    def normalize_bin_number(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_bin_number(value)


class BinCreate(BinBase):
    bin_number: str
    cabinet_id: int


class BinUpdate(BaseModel):
    label: Optional[str] = None
    bin_number: Optional[str] = None
    group_number: Optional[int] = None
    location_note: Optional[str] = None
    description: Optional[str] = None
    requires_full_bin_checkout: Optional[bool] = None

    @field_validator("bin_number")
    @classmethod
    def normalize_bin_number(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_bin_number(value)


class BinOut(BinBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cabinet_id: int
    qr_code_token: Optional[str] = None
    created_at: datetime
    updated_at: datetime
