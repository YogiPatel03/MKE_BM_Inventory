from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.bin import Bin
    from app.models.item import Item
    from app.models.user import User


class RequestStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


class InventoryRequest(Base):
    """
    A user's request to check out an item or bin.

    USER role cannot directly create Transactions — they submit a Request
    which is then approved or denied by GROUP_LEAD+.

    When approved, the approver (or system) creates the Transaction/BinTransaction.
    Fulfilled = approved and transaction created.

    item_id XOR bin_id: a request targets either an item or a full bin, not both.
    """

    __tablename__ = "inventory_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    approver_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("items.id"), nullable=True, index=True
    )
    bin_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("bins.id"), nullable=True, index=True
    )

    quantity_requested: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RequestStatus.PENDING, index=True
    )

    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    denial_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fulfilled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Telegram notification tracking
    telegram_message_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    requester: Mapped["User"] = relationship(
        "User", foreign_keys=[requester_id], back_populates="requests_made"
    )
    approver: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[approver_id], back_populates="requests_approved"
    )
    item: Mapped[Optional["Item"]] = relationship(
        "Item", back_populates="requests", foreign_keys=[item_id]
    )
    bin: Mapped[Optional["Bin"]] = relationship(
        "Bin", back_populates="requests", foreign_keys=[bin_id]
    )

    def __repr__(self) -> str:
        target = f"item={self.item_id}" if self.item_id else f"bin={self.bin_id}"
        return f"<InventoryRequest {self.id} {target} status={self.status}>"
