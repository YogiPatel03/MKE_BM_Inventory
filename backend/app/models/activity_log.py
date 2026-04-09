from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.bin import Bin
    from app.models.cabinet import Cabinet
    from app.models.item import Item
    from app.models.user import User


class ActivityType:
    # Item lifecycle
    ITEM_CREATED = "ITEM_CREATED"
    ITEM_EDITED = "ITEM_EDITED"
    ITEM_DEACTIVATED = "ITEM_DEACTIVATED"
    ITEM_REACTIVATED = "ITEM_REACTIVATED"
    # Cabinet / bin
    CABINET_EDITED = "CABINET_EDITED"
    # User management
    USER_EDITED = "USER_EDITED"
    USER_PASSWORD_RESET = "USER_PASSWORD_RESET"
    # Transactions
    ITEM_CHECKED_OUT = "ITEM_CHECKED_OUT"
    ITEM_RETURNED = "ITEM_RETURNED"
    BIN_CHECKED_OUT = "BIN_CHECKED_OUT"
    BIN_RETURNED = "BIN_RETURNED"
    # Consumables
    USAGE_RECORDED = "USAGE_RECORDED"
    USAGE_REVERSED = "USAGE_REVERSED"
    # Stock
    STOCK_ADJUSTMENT_INCREASE = "STOCK_ADJUSTMENT_INCREASE"
    STOCK_ADJUSTMENT_DECREASE = "STOCK_ADJUSTMENT_DECREASE"
    PURCHASE_LOGGED = "PURCHASE_LOGGED"
    # Location
    ITEM_MOVED = "ITEM_MOVED"
    BIN_MOVED = "BIN_MOVED"
    ITEM_MOVED_TO_RESTOCK = "ITEM_MOVED_TO_RESTOCK"
    ITEM_RESTORED_FROM_RESTOCK = "ITEM_RESTORED_FROM_RESTOCK"
    # Requests
    REQUEST_FULFILLED = "REQUEST_FULFILLED"


class ActivityLog(Base):
    """
    Unified, append-only audit ledger. Every inventory event creates one row here.

    The underlying domain records (Transaction, UsageEvent, etc.) remain the
    authoritative detail source. ActivityLog references them via source_type/source_id
    and provides a single queryable feed for the Transactions UI.

    actor_id may be None for system-generated events (e.g. Restock Me auto-moves).
    """

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Who performed the action (None = system)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)

    # What was affected
    target_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("items.id"), nullable=True, index=True)
    target_bin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bins.id"), nullable=True)
    target_cabinet_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cabinets.id"), nullable=True)
    target_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Quantity / cost context (signed: positive = increase, negative = decrease)
    quantity_delta: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cost_impact: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Structured before/after data for edits, metadata for other types
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)

    # Reference to the source domain record
    source_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    actor: Mapped[Optional["User"]] = relationship("User", foreign_keys=[actor_id])
    target_item: Mapped[Optional["Item"]] = relationship("Item", foreign_keys=[target_item_id])
    target_bin: Mapped[Optional["Bin"]] = relationship("Bin", foreign_keys=[target_bin_id])
    target_cabinet: Mapped[Optional["Cabinet"]] = relationship("Cabinet", foreign_keys=[target_cabinet_id])
    target_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[target_user_id])

    def __repr__(self) -> str:
        return f"<ActivityLog {self.id} {self.activity_type}>"
