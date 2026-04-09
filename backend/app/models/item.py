from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.bin import Bin
    from app.models.cabinet import Cabinet
    from app.models.inventory_request import InventoryRequest
    from app.models.purchase_record import PurchaseRecord
    from app.models.stock_adjustment import StockAdjustment
    from app.models.transaction import Transaction
    from app.models.usage_event import UsageEvent


class ItemCondition:
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    DAMAGED = "DAMAGED"


class Item(Base):
    """
    A trackable inventory object. Lives in a cabinet, optionally in a bin.

    quantity_available is a cached/denormalized field updated atomically during
    checkout and return. Transaction is the authoritative audit source for history.

    is_consumable=True items use UsageEvent (mark-as-used) rather than checkout/return.
    Items inside a bin (bin_id IS NOT NULL) may only be checked out via BinTransaction.
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

    # Consumable vs non-consumable
    is_consumable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Current unit price (mutable — PurchaseRecord stores historical pricing)
    unit_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    # QR code token for bin scanning
    qr_code_token: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, unique=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    cabinet: Mapped["Cabinet"] = relationship("Cabinet", back_populates="items")
    bin: Mapped[Optional["Bin"]] = relationship("Bin", back_populates="items")
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="item")
    usage_events: Mapped[List["UsageEvent"]] = relationship("UsageEvent", back_populates="item")
    stock_adjustments: Mapped[List["StockAdjustment"]] = relationship(
        "StockAdjustment", back_populates="item"
    )
    purchase_records: Mapped[List["PurchaseRecord"]] = relationship(
        "PurchaseRecord", back_populates="item"
    )
    requests: Mapped[List["InventoryRequest"]] = relationship(
        "InventoryRequest", back_populates="item", foreign_keys="InventoryRequest.item_id"
    )

    def generate_qr_token(self) -> str:
        token = str(uuid.uuid4())
        self.qr_code_token = token
        return token

    def __repr__(self) -> str:
        return f"<Item {self.name} ({self.quantity_available}/{self.quantity_total})>"
