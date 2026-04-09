from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.item import Item
    from app.models.user import User


class AdjustmentReason:
    RESTOCK = "RESTOCK"
    DAMAGE = "DAMAGE"
    LOSS = "LOSS"
    CORRECTION = "CORRECTION"
    FOUND = "FOUND"
    OTHER = "OTHER"


class StockAdjustment(Base):
    """
    Auditable record of manual quantity changes to an item.

    Used when inventory counts need correction outside normal
    checkout/return flow (e.g., physical audit, damage, restock).
    Updates both quantity_total and quantity_available atomically.

    delta is signed: positive = adding stock, negative = removing stock.
    """

    __tablename__ = "stock_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False, index=True)
    adjusted_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_before: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_after: Mapped[int] = mapped_column(Integer, nullable=False)

    reason: Mapped[str] = mapped_column(String(50), nullable=False, default=AdjustmentReason.CORRECTION)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    adjusted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    item: Mapped["Item"] = relationship("Item", back_populates="stock_adjustments")
    adjusted_by: Mapped["User"] = relationship("User", back_populates="stock_adjustments")

    def __repr__(self) -> str:
        return f"<StockAdjustment {self.id} item={self.item_id} delta={self.delta:+d}>"
