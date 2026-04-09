from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.bin_transaction import BinTransaction
    from app.models.cabinet import Cabinet
    from app.models.inventory_request import InventoryRequest
    from app.models.item import Item


class Bin(Base):
    """
    A sub-container inside a cabinet.

    Bins are physical location anchors. Items inside a bin are checked out
    as a unit via BinTransaction — individual item checkout is blocked for binned items.
    """

    __tablename__ = "bins"

    id: Mapped[int] = mapped_column(primary_key=True)
    cabinet_id: Mapped[int] = mapped_column(ForeignKey("cabinets.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    group_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    location_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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

    cabinet: Mapped["Cabinet"] = relationship("Cabinet", back_populates="bins")
    items: Mapped[List["Item"]] = relationship("Item", foreign_keys="Item.bin_id", back_populates="bin")
    bin_transactions: Mapped[List["BinTransaction"]] = relationship(
        "BinTransaction", back_populates="bin"
    )
    requests: Mapped[List["InventoryRequest"]] = relationship(
        "InventoryRequest", back_populates="bin", foreign_keys="InventoryRequest.bin_id"
    )

    def generate_qr_token(self) -> str:
        token = str(uuid.uuid4())
        self.qr_code_token = token
        return token

    def __repr__(self) -> str:
        return f"<Bin {self.label} in cabinet {self.cabinet_id}>"
