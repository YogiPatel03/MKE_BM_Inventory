from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.item import Item
    from app.models.user import User


class UsageEvent(Base):
    """
    Records consumption of a consumable item (is_consumable=True).

    Consumables are marked as used rather than checked out/returned.
    This decrements quantity_available and quantity_total permanently
    (the item is consumed, not returned). Transaction is NOT used for
    consumables — UsageEvent is the audit trail.
    """

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    processed_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    quantity_used: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    item: Mapped["Item"] = relationship("Item", back_populates="usage_events")
    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="usage_events"
    )
    processed_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[processed_by_user_id], back_populates="processed_usage_events"
    )

    def __repr__(self) -> str:
        return f"<UsageEvent {self.id} item={self.item_id} qty={self.quantity_used}>"
