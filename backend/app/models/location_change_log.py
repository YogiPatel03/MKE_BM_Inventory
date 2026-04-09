from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class LocationChangeLog(Base):
    """
    Immutable audit trail for item and bin location changes.

    entity_type: 'item' or 'bin'
    entity_id: the item.id or bin.id that moved

    For items: from/to cabinet_id and bin_id (bin_id nullable = not in a bin)
    For bins: from/to cabinet_id only
    """

    __tablename__ = "location_change_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    moved_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    from_cabinet_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cabinets.id"), nullable=True
    )
    to_cabinet_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cabinets.id"), nullable=True
    )
    from_bin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bins.id"), nullable=True)
    to_bin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bins.id"), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    moved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    move_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    moved_by: Mapped[Optional["User"]] = relationship("User", back_populates="location_changes")

    def __repr__(self) -> str:
        return f"<LocationChangeLog {self.id} {self.entity_type}={self.entity_id}>"
