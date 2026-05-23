from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


def sabha_date_for_week(week_start: date) -> date:
    """
    Compute the Sabha date (Sunday) for a given prep-week start date.

    The prep-week checklist is prepared during week_start…week_start+6 and
    used at Sabha on the Sunday of that same week.

    Special case: if week_start is itself a Sunday (weekday=6), Sabha is the
    NEXT Sunday (+7 days) because week_start then represents the day *before*
    the coming prep week.  This supports legacy or test data with Sunday
    week_starts.

    Examples:
        week_start=2026-05-04 (Mon) → sabha=2026-05-10 (Sun)  [+6 days]
        week_start=2026-05-03 (Sun) → sabha=2026-05-10 (Sun)  [+7 days]
    """
    # weekday(): Mon=0 … Sun=6
    days = (6 - week_start.weekday()) % 7  # days until the coming Sunday
    return week_start + timedelta(days=days if days != 0 else 7)


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


class SubchecklistType:
    PRE_SABHA = "PRE_SABHA"
    POST_SABHA = "POST_SABHA"
    CUSTOM = "CUSTOM"


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
        order_by="ChecklistItem.item_order",
        foreign_keys="ChecklistItem.checklist_id",
    )
    assignments: Mapped[List["ChecklistAssignment"]] = relationship(
        "ChecklistAssignment", back_populates="checklist", cascade="all, delete-orphan"
    )
    subchecklists: Mapped[List["Subchecklist"]] = relationship(
        "Subchecklist", back_populates="checklist", cascade="all, delete-orphan",
        order_by="Subchecklist.section_order"
    )

    def __repr__(self) -> str:
        return f"<Checklist {self.group_name} week={self.week_start}>"


class Subchecklist(Base):
    """
    A section within a weekly checklist (e.g., Pre Sabha, Post Sabha, or custom).
    Two mandatory subchecklists are always present: PRE_SABHA and POST_SABHA.
    """

    __tablename__ = "subchecklists"

    id: Mapped[int] = mapped_column(primary_key=True)
    checklist_id: Mapped[int] = mapped_column(ForeignKey("checklists.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    section_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SubchecklistType.CUSTOM
    )  # PRE_SABHA | POST_SABHA | CUSTOM
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    section_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    checklist: Mapped["Checklist"] = relationship("Checklist", back_populates="subchecklists")
    items: Mapped[List["ChecklistItem"]] = relationship(
        "ChecklistItem", back_populates="subchecklist",
        order_by="ChecklistItem.item_order",
        foreign_keys="ChecklistItem.subchecklist_id",
    )

    def __repr__(self) -> str:
        return f"<Subchecklist {self.id} '{self.title}' type={self.section_type}>"


class ChecklistItem(Base):
    """A single task within a weekly checklist."""

    __tablename__ = "checklist_items"
    __table_args__ = (
        Index(
            "uq_checklist_item_linked_txn",
            "linked_transaction_id",
            unique=True,
            sqlite_where=text("linked_transaction_id IS NOT NULL"),
            postgresql_where=text("linked_transaction_id IS NOT NULL"),
        ),
        Index(
            "uq_checklist_item_linked_bin_txn",
            "linked_bin_transaction_id",
            unique=True,
            sqlite_where=text("linked_bin_transaction_id IS NOT NULL"),
            postgresql_where=text("linked_bin_transaction_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    checklist_id: Mapped[int] = mapped_column(ForeignKey("checklists.id"), nullable=False, index=True)
    subchecklist_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subchecklists.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    item_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Per-task assignee. NULL means "Everyone" — one completion counts for all.
    assignee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

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

    checklist: Mapped["Checklist"] = relationship(
        "Checklist", back_populates="items", foreign_keys=[checklist_id]
    )
    subchecklist: Mapped[Optional["Subchecklist"]] = relationship(
        "Subchecklist", back_populates="items", foreign_keys=[subchecklist_id]
    )
    completed_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[completed_by_user_id])
    assignee: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assignee_id])

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


class ChecklistAssignmentDefault(Base):
    """
    Persistent default assignees for a group's recurring weekly checklist.
    When a new weekly checklist is generated, these defaults are copied onto it
    as ChecklistAssignment rows. Admins/coordinators may override per-week
    assignments without touching these defaults.

    Uniqueness: only one active default per (group_name, user_id). A partial
    unique index (WHERE is_active) is created by migration 022 so that
    deactivated rows are preserved for history but a user may be re-added.
    """

    __tablename__ = "checklist_assignment_defaults"
    __table_args__ = (
        # Non-unique lookup index; the partial unique constraint is in the migration.
        Index("ix_checklist_defaults_group_user", "group_name", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    assigned_by: Mapped["User"] = relationship("User", foreign_keys=[assigned_by_id])

    def __repr__(self) -> str:
        return f"<ChecklistAssignmentDefault group={self.group_name} user={self.user_id} active={self.is_active}>"
