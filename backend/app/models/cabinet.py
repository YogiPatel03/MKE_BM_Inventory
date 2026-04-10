from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.bin import Bin
    from app.models.item import Item
    from app.models.room import Room


class Cabinet(Base):
    """
    Physical storage unit that lives inside a Room.

    Structure: Room > Cabinet > (Bins and/or Items)
    Items can belong to a cabinet without being inside a bin — the bin_id
    on Item is nullable to represent this.
    """

    __tablename__ = "cabinets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Every cabinet must belong to a room
    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id"), nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    room: Mapped["Room"] = relationship("Room", back_populates="cabinets")
    bins: Mapped[List["Bin"]] = relationship(
        "Bin", back_populates="cabinet", cascade="all, delete-orphan"
    )
    items: Mapped[List["Item"]] = relationship(
        "Item", foreign_keys="Item.cabinet_id", back_populates="cabinet"
    )

    def __repr__(self) -> str:
        return f"<Cabinet {self.name}>"
