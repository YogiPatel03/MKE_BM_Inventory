from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.bin import Bin
    from app.models.transaction import Transaction
    from app.models.user import User


class BinTransactionStatus(str, Enum):
    CHECKED_OUT = "CHECKED_OUT"
    RETURNED = "RETURNED"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class BinTransaction(Base):
    """
    Checkout/return of an entire bin as a unit.

    When a bin is checked out, all items inside are checked out simultaneously
    and individual item checkout is blocked until the bin is returned.
    Individual Transaction records are created for each item and linked here
    via Transaction.bin_transaction_id.
    """

    __tablename__ = "bin_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    bin_id: Mapped[int] = mapped_column(ForeignKey("bins.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    processed_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BinTransactionStatus.CHECKED_OUT, index=True
    )

    checked_out_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    returned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    bin: Mapped["Bin"] = relationship("Bin", back_populates="bin_transactions")
    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="bin_transactions"
    )
    processed_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[processed_by_user_id], back_populates="processed_bin_transactions"
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="bin_transaction"
    )

    def __repr__(self) -> str:
        return f"<BinTransaction {self.id} bin={self.bin_id} user={self.user_id} status={self.status}>"
