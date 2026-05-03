from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# ── Assignment ────────────────────────────────────────────────────────────────

class AssignmentUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    username: str
    group_name: Optional[str] = None


class ChecklistAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    checklist_id: int
    user_id: int
    assigned_by_id: int
    assigned_at: datetime
    user: AssignmentUserOut


class ChecklistAssignCreate(BaseModel):
    user_id: int


# ── Subchecklist ──────────────────────────────────────────────────────────────

class SubchecklistCreate(BaseModel):
    title: str
    section_type: str = "CUSTOM"  # PRE_SABHA | POST_SABHA | CUSTOM
    section_order: Optional[int] = None


class SubchecklistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    checklist_id: int
    title: str
    section_type: str
    is_mandatory: bool
    section_order: int
    created_at: datetime
    updated_at: datetime
    items: List["ChecklistItemOut"] = []


# ── Checklist Items ───────────────────────────────────────────────────────────

class ChecklistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    checklist_id: int
    subchecklist_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    item_order: int
    assignee_id: Optional[int] = None
    assignee: Optional[AssignmentUserOut] = None
    is_auto_generated: bool
    auto_type: Optional[str] = None
    linked_transaction_id: Optional[int] = None
    linked_bin_transaction_id: Optional[int] = None
    is_completed: bool
    completed_at: Optional[datetime] = None
    completed_by_user_id: Optional[int] = None
    completion_notes: Optional[str] = None
    photo_requested_via_telegram: bool
    created_at: datetime
    updated_at: datetime


class ChecklistItemCreate(BaseModel):
    title: str
    description: Optional[str] = None
    item_order: Optional[int] = 0
    assignee_id: Optional[int] = None
    subchecklist_id: Optional[int] = None


class ChecklistItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_id: Optional[int] = None


class ChecklistItemComplete(BaseModel):
    notes: Optional[str] = None


# ── Checklist ─────────────────────────────────────────────────────────────────

class ChecklistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    group_name: str
    week_start: date
    is_active: bool
    created_at: datetime
    updated_at: datetime
    items: List[ChecklistItemOut] = []
    assignments: List[ChecklistAssignmentOut] = []
    subchecklists: List[SubchecklistOut] = []


class ChecklistSummary(BaseModel):
    """Lighter version for list views (no items)."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    group_name: str
    week_start: date
    is_active: bool
    created_at: datetime
    updated_at: datetime
    item_count: int = 0
    completed_count: int = 0
    assignee_count: int = 0


# Forward reference resolution
SubchecklistOut.model_rebuild()
