from __future__ import annotations

from typing import TYPE_CHECKING, List

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Role(Base):
    """
    Defines a permission set for a class of users.

    Roles are created by seed/migration and referenced by User.
    Boolean flags drive all authorization checks — no magic strings
    in business logic. The four built-in roles are:
      ADMIN       — full system access, manages users
      COORDINATOR — manages inventory and processes any transaction
      GROUP_LEAD  — processes transactions, views full history
      USER        — checks out / returns their own items
    """

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # Inventory permissions
    can_manage_inventory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_manage_cabinets: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_manage_bins: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # User management
    can_manage_users: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Transaction permissions
    can_process_any_transaction: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_view_all_transactions: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Audit
    can_view_audit_logs: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    users: Mapped[List["User"]] = relationship("User", back_populates="role")

    def __repr__(self) -> str:
        return f"<Role {self.name}>"
