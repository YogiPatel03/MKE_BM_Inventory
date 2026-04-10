from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.cabinet import Cabinet


class Room(Base):
    """
    Top-level physical space that contains cabinets.

    Structure: Room > Cabinet > (Bins and/or Items)
    Only admins can create/edit/delete rooms.
    """

    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    cabinets: Mapped[List["Cabinet"]] = relationship(
        "Cabinet", back_populates="room"
    )

    def __repr__(self) -> str:
        return f"<Room {self.name}>"
