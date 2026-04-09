from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.item import Item
    from app.models.receipt_record import ReceiptRecord
    from app.models.user import User


class PurchaseRecord(Base):
    """
    Records a purchase event for an item — historical pricing and restocking.

    Each purchase can optionally link to a ReceiptRecord (scanned or uploaded receipt).
    unit_price at time of purchase is stored here; Item.unit_price is updated to reflect
    the most recent purchase price.
    """

    __tablename__ = "purchase_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False, index=True)
    purchased_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    receipt_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("receipt_records.id"), nullable=True
    )

    quantity_purchased: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    total_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    vendor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    purchased_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    item: Mapped["Item"] = relationship("Item", back_populates="purchase_records")
    purchased_by: Mapped["User"] = relationship("User", back_populates="purchase_records")
    receipt: Mapped[Optional["ReceiptRecord"]] = relationship(
        "ReceiptRecord", back_populates="purchase_records"
    )

    def __repr__(self) -> str:
        return f"<PurchaseRecord {self.id} item={self.item_id} qty={self.quantity_purchased}>"
