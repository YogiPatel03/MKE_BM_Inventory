from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.transaction import Transaction
    from app.models.user import User


class TransactionPhoto(Base):
    """
    Proof record for a transaction. In v1, photos are submitted via Telegram
    rather than uploaded through the web app. This table stores the Telegram
    message ID and file ID as the proof reference.

    telegram_file_id: Telegram's persistent file identifier — can be used to
      fetch the photo from Telegram servers or resend it.
    telegram_message_id: The message ID in the coordinator channel where the
      photo was posted, for direct linking or reference.

    When in-app upload is added in a future version, add a file_url column
    and update the upload handler. The Telegram fields remain for backward
    compatibility with bot-provided proofs.
    """

    __tablename__ = "transaction_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id"), nullable=False, index=True
    )
    uploaded_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    # Telegram-sourced proof fields
    telegram_message_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    telegram_file_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    transaction: Mapped["Transaction"] = relationship("Transaction", back_populates="photos")
    uploaded_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[uploaded_by_user_id]
    )

    def __repr__(self) -> str:
        return f"<TransactionPhoto {self.id} for transaction {self.transaction_id}>"
