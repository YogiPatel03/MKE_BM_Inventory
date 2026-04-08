from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.item import Item
    from app.models.transaction_photo import TransactionPhoto
    from app.models.user import User


class TransactionStatus(str, Enum):
    CHECKED_OUT = "CHECKED_OUT"
    RETURNED = "RETURNED"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class Transaction(Base):
    """
    The authoritative record of item movement. Every checkout and return
    is captured here. This is the single source of truth for audit history.

    The Transaction model replaces any checked_out_by / checked_out_at fields
    on Item or Bin. Item.quantity_available is a denormalized cache; Transaction
    is the ground truth.

    processed_by_user_id: the staff member who physically processed the
    transaction (may differ from user_id when a coordinator checks out on
    behalf of a user).

    photo_requested_via_telegram: set True when a return is logged without
    an attached photo and the bot has been asked to request one in the
    coordinator channel.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_transaction_qty_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    processed_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TransactionStatus.CHECKED_OUT, index=True
    )

    checked_out_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    returned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photo_requested_via_telegram: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    photo_request_message_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    item: Mapped["Item"] = relationship("Item", back_populates="transactions")
    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="transactions"
    )
    processed_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[processed_by_user_id], back_populates="processed_transactions"
    )
    photos: Mapped[List["TransactionPhoto"]] = relationship(
        "TransactionPhoto", back_populates="transaction", cascade="all, delete-orphan"
    )

    @property
    def is_overdue(self) -> bool:
        if self.due_at and self.status == TransactionStatus.CHECKED_OUT:
            return datetime.utcnow() > self.due_at.replace(tzinfo=None)
        return False

    def __repr__(self) -> str:
        return f"<Transaction {self.id} item={self.item_id} user={self.user_id} status={self.status}>"
