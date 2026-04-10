from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class GroupName:
    """Team/group identifiers for weekly checklists."""
    SHISHU_MANDAL = "SHISHU_MANDAL"
    GROUP_1 = "GROUP_1"
    GROUP_2 = "GROUP_2"
    GROUP_3 = "GROUP_3"

    ALL = ["SHISHU_MANDAL", "GROUP_1", "GROUP_2", "GROUP_3"]

    DISPLAY = {
        "SHISHU_MANDAL": "Shishu Mandal",
        "GROUP_1": "Group 1",
        "GROUP_2": "Group 2",
        "GROUP_3": "Group 3",
    }


class Checklist(Base):
    """
    Weekly checklist for one group (one per group per week).
    Auto-generated every Monday. Active through Sunday.
    """

    __tablename__ = "checklists"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)  # Always Monday
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    items: Mapped[List["ChecklistItem"]] = relationship(
        "ChecklistItem", back_populates="checklist", cascade="all, delete-orphan",
        order_by="ChecklistItem.item_order"
    )
    assignments: Mapped[List["ChecklistAssignment"]] = relationship(
        "ChecklistAssignment", back_populates="checklist", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Checklist {self.group_name} week={self.week_start}>"


class ChecklistItem(Base):
    """A single task within a weekly checklist."""

    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    checklist_id: Mapped[int] = mapped_column(ForeignKey("checklists.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    item_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Auto-generated return tasks
    is_auto_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # "ITEM_RETURN" | "BIN_RETURN" | None (for manual items)
    auto_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    linked_transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    linked_bin_transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("bin_transactions.id", ondelete="SET NULL"), nullable=True
    )

    # Completion (checklist-item level — shared across all assignees)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    completion_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photo_requested_via_telegram: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    checklist: Mapped["Checklist"] = relationship("Checklist", back_populates="items")
    completed_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[completed_by_user_id])

    def __repr__(self) -> str:
        return f"<ChecklistItem {self.id} '{self.title[:30]}'>"


class ChecklistAssignment(Base):
    """Assignment of a user to a weekly checklist."""

    __tablename__ = "checklist_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    checklist_id: Mapped[int] = mapped_column(ForeignKey("checklists.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    checklist: Mapped["Checklist"] = relationship("Checklist", back_populates="assignments")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    assigned_by: Mapped["User"] = relationship("User", foreign_keys=[assigned_by_id])

    def __repr__(self) -> str:
        return f"<ChecklistAssignment checklist={self.checklist_id} user={self.user_id}>"
