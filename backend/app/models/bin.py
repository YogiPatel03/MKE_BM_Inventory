from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.cabinet import Cabinet
    from app.models.item import Item


class Bin(Base):
    """
    A sub-container inside a cabinet. Bins organize items spatially.

    Bins are physical location anchors — they do NOT own checkout state.
    The Transaction model is the authoritative source for item movement history.
    """

    __tablename__ = "bins"

    id: Mapped[int] = mapped_column(primary_key=True)
    cabinet_id: Mapped[int] = mapped_column(ForeignKey("cabinets.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    group_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    location_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    cabinet: Mapped["Cabinet"] = relationship("Cabinet", back_populates="bins")
    items: Mapped[List["Item"]] = relationship("Item", back_populates="bin")

    def __repr__(self) -> str:
        return f"<Bin {self.label} in cabinet {self.cabinet_id}>"
