from fastapi import HTTPException, status

from app.models.user import User


def require_manage_inventory(user: User) -> None:
    if not (user.role.can_manage_inventory or user.role.can_manage_users):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Inventory management permission required")


def require_manage_cabinets(user: User) -> None:
    if not (user.role.can_manage_cabinets or user.role.can_manage_users):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cabinet management permission required")


def require_manage_bins(user: User) -> None:
    if not (user.role.can_manage_bins or user.role.can_manage_users):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bin management permission required")


def require_manage_users(user: User) -> None:
    if not user.role.can_manage_users:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User management permission required")


def require_process_any_transaction(user: User) -> None:
    if not (user.role.can_process_any_transaction or user.role.can_manage_users):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Transaction processing permission required")


def require_view_all_transactions(user: User) -> None:
    if not (user.role.can_view_all_transactions or user.role.can_manage_users):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission to view all transactions required")


def require_view_audit_logs(user: User) -> None:
    if not (user.role.can_view_audit_logs or user.role.can_manage_users):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Audit log access required")


def can_process_transaction_for(actor: User, target_user_id: int) -> bool:
    """
    Returns True if `actor` is allowed to initiate a transaction on behalf of
    target_user_id. Users can always act for themselves; coordinators and admins
    can act for anyone.
    """
    if actor.id == target_user_id:
        return True
    return actor.role.can_process_any_transaction or actor.role.can_manage_users
