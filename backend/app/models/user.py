from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.role import Role
    from app.models.transaction import Transaction


class User(Base):
    """
    A system account. Accounts are admin-created; no self-registration.

    telegramChatId is set when the user runs /link <token> in the bot.
    It enables DM notifications for overdue items and personalized bot replies.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    telegram_handle: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    telegram_link_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    role: Mapped["Role"] = relationship("Role", back_populates="users")

    # Transactions initiated by this user
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction",
        foreign_keys="Transaction.user_id",
        back_populates="user",
    )
    # Transactions this user processed on behalf of another
    processed_transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction",
        foreign_keys="Transaction.processed_by_user_id",
        back_populates="processed_by",
    )

    def __repr__(self) -> str:
        return f"<User {self.username}>"
