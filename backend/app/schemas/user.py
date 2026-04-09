from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    can_manage_inventory: bool
    can_manage_cabinets: bool
    can_manage_bins: bool
    can_manage_users: bool
    can_process_any_transaction: bool
    can_view_all_transactions: bool
    can_view_audit_logs: bool
    can_approve_requests: bool


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    username: str
    telegram_handle: Optional[str]
    telegram_chat_id: Optional[str]
    role_id: int
    role: RoleOut
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    full_name: str
    username: str
    password: str
    role_id: int
    telegram_handle: Optional[str] = None

    @field_validator("username")
    @classmethod
    def username_lowercase(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    username: Optional[str] = None
    telegram_handle: Optional[str] = None
    role_id: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("username")
    @classmethod
    def username_lowercase(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().lower() if v else v


class PasswordResetRequest(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class TelegramLinkToken(BaseModel):
    token: str
    instructions: str
