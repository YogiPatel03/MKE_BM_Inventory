from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.purchase_record import PurchaseRecord
    from app.models.user import User


class ReceiptRecord(Base):
    """
    A receipt image or document associated with one or more purchases.

    file_path: relative path on the server (or object storage key).
    uploaded_via: 'web' | 'telegram' — tracks how receipt was submitted.

    After a PurchaseRecord is created, the Telegram bot may request a receipt
    photo in the coordinator channel. When received, a ReceiptRecord is created
    and linked to the purchase.
    """

    __tablename__ = "receipt_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    uploaded_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    total_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    vendor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    uploaded_via: Mapped[str] = mapped_column(String(20), nullable=False, default="web")

    # Telegram tracking: message_id of the receipt request in coordinator channel
    telegram_request_message_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    # Telegram file_id of the receipt photo once received
    telegram_file_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    uploaded_by: Mapped[Optional["User"]] = relationship(
        "User", back_populates="receipt_records"
    )
    purchase_records: Mapped[List["PurchaseRecord"]] = relationship(
        "PurchaseRecord", back_populates="receipt"
    )

    def __repr__(self) -> str:
        return f"<ReceiptRecord {self.id} via={self.uploaded_via}>"
