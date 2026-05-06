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


def require_approve_requests(user: User) -> None:
    if not (user.role.can_approve_requests or user.role.can_manage_users):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Request approval permission required")


def is_group_lead(user: User) -> bool:
    return user.role.can_approve_requests and user.group_name is not None


def check_request_scope(current_user: User, requester_group: str | None) -> bool:
    """
    Returns True if current_user may approve/deny a request from a user in requester_group.
    Mirrors the scoping logic used by list_requests:
      - can_manage_users → global access
      - GROUP_LEAD (can_approve_requests + group_name set) → own group only
      - can_approve_requests without group_name (COORDINATOR) → global access
    """
    if current_user.role.can_manage_users:
        return True
    if is_group_lead(current_user):
        return requester_group is not None and requester_group == current_user.group_name
    return current_user.role.can_approve_requests


def can_process_transaction_for(
    actor: User, target_user_id: int, target_group: str | None = None
) -> bool:
    """
    Returns True if `actor` is allowed to initiate a transaction on behalf of
    target_user_id. Users can always act for themselves; coordinators and admins
    can act for anyone; GROUP_LEAD can act for members of their own group.
    """
    if actor.id == target_user_id:
        return True
    if actor.role.can_process_any_transaction or actor.role.can_manage_users:
        return True
    if is_group_lead(actor) and target_group is not None and target_group == actor.group_name:
        return True
    return False
