from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.bin import Bin
    from app.models.cabinet import Cabinet
    from app.models.transaction import Transaction


class ItemCondition:
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    DAMAGED = "DAMAGED"


class Item(Base):
    """
    A trackable inventory object. Items live in a cabinet and optionally in a bin.

    quantity_available is a cached/denormalized field updated atomically during
    checkout and return. Transaction is the authoritative audit source — do not
    rely on this field for history. It exists only for fast availability queries.

    bin_id is nullable: a null bin_id means the item lives directly in the cabinet.
    """

    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint("quantity_available >= 0", name="ck_item_qty_available_non_negative"),
        CheckConstraint("quantity_total >= 0", name="ck_item_qty_total_non_negative"),
        CheckConstraint(
            "quantity_available <= quantity_total", name="ck_item_qty_available_lte_total"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Denormalized availability cache. Transaction is the source of truth for history.
    quantity_total: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    quantity_available: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    cabinet_id: Mapped[int] = mapped_column(ForeignKey("cabinets.id"), nullable=False, index=True)
    bin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bins.id"), nullable=True, index=True)

    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, unique=True)
    condition: Mapped[str] = mapped_column(String(20), nullable=False, default=ItemCondition.GOOD)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    cabinet: Mapped["Cabinet"] = relationship("Cabinet", back_populates="items")
    bin: Mapped[Optional["Bin"]] = relationship("Bin", back_populates="items")
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="item")

    def __repr__(self) -> str:
        return f"<Item {self.name} ({self.quantity_available}/{self.quantity_total})>"
