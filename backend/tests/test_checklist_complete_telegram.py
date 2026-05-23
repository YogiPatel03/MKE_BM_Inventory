"""
Tests for Telegram notifications on checklist item complete/incomplete.

Covers:
1. Manual complete sends notify_checklist_item_status_changed("completed")
2. Manual incomplete sends notify_checklist_item_status_changed("incomplete")
3. Telegram failure during complete does NOT rollback DB
4. Telegram failure during incomplete does NOT rollback DB
5. Incomplete endpoint clears completed_at / completed_by_user_id
6. Cross-group user cannot mark another group's item incomplete (403)
7. auto_complete_return_task_for_transaction does NOT call the new notification
"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import hash_password
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.checklist import (
    Checklist,
    ChecklistAssignment,
    ChecklistItem,
    GroupName,
)
from app.models.role import Role
from app.models.user import User


# ─── Role factories ────────────────────────────────────────────────────────────

def _admin_role() -> Role:
    return Role(
        name="ADMIN",
        can_manage_inventory=True,
        can_manage_cabinets=True,
        can_manage_bins=True,
        can_manage_users=True,
        can_process_any_transaction=True,
        can_view_all_transactions=True,
        can_view_audit_logs=True,
        can_approve_requests=True,
    )


def _user_role() -> Role:
    return Role(
        name="USER",
        can_manage_inventory=False,
        can_manage_cabinets=False,
        can_manage_bins=False,
        can_manage_users=False,
        can_process_any_transaction=False,
        can_view_all_transactions=False,
        can_view_audit_logs=False,
        can_approve_requests=False,
    )


# ─── Seed helpers ──────────────────────────────────────────────────────────────

async def _seed_user(
    db: AsyncSession,
    *,
    role: Role,
    username: str,
    group_name: str | None = None,
) -> User:
    user = User(
        full_name="Test User",
        username=username,
        password_hash=hash_password("pass"),
        role_id=role.id,
        group_name=group_name,
    )
    db.add(user)
    await db.flush()
    return user


async def _seed_checklist(
    db: AsyncSession,
    *,
    group_name: str,
    week_start: date,
) -> Checklist:
    cl = Checklist(group_name=group_name, week_start=week_start, is_active=True)
    db.add(cl)
    await db.flush()
    return cl


async def _assign(db: AsyncSession, checklist: Checklist, user: User, assigned_by: User) -> None:
    db.add(ChecklistAssignment(
        checklist_id=checklist.id,
        user_id=user.id,
        assigned_by_id=assigned_by.id,
    ))
    await db.flush()


async def _seed_task(
    db: AsyncSession,
    checklist: Checklist,
    *,
    title: str = "Test task",
    is_auto_generated: bool = False,
    auto_type: str | None = None,
    is_completed: bool = False,
) -> ChecklistItem:
    task = ChecklistItem(
        checklist_id=checklist.id,
        title=title,
        is_auto_generated=is_auto_generated,
        auto_type=auto_type,
        is_completed=is_completed,
    )
    db.add(task)
    await db.flush()
    return task


# ─── client_as fixture ─────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client_as(db):
    """Factory: client_as(user) → authenticated AsyncClient sharing the test db."""
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    def make_client(user: User):
        app.dependency_overrides[get_current_user] = lambda: user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield make_client
    app.dependency_overrides.clear()


# ─── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_manual_complete_sends_status_changed_notification(db: AsyncSession, client_as):
    """Manual complete fires notify_checklist_item_status_changed with 'completed'."""
    admin_role = _admin_role()
    db.add(admin_role)
    await db.flush()
    admin = await _seed_user(db, role=admin_role, username="admin_complete1", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)  # Monday
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _assign(db, cl, admin, admin)
    task = await _seed_task(db, cl, title="Set up chairs")
    await db.commit()

    with patch(
        "app.routers.checklists.notify_checklist_item_status_changed",
        new_callable=AsyncMock,
    ) as mock_notify:
        async with client_as(admin) as c:
            resp = await c.patch(
                f"/api/checklists/{cl.id}/items/{task.id}/complete",
                json={"notes": "All done"},
            )
        assert resp.status_code == 200

    mock_notify.assert_called_once()
    _task, _cl, _actor, status_arg = mock_notify.call_args.args
    assert status_arg == "completed"
    assert _task.id == task.id
    assert _cl.id == cl.id
    assert _actor.id == admin.id


@pytest.mark.asyncio
async def test_manual_incomplete_sends_status_changed_notification(db: AsyncSession, client_as):
    """Manual incomplete fires notify_checklist_item_status_changed with 'incomplete'."""
    admin_role = _admin_role()
    db.add(admin_role)
    await db.flush()
    admin = await _seed_user(db, role=admin_role, username="admin_incomplete1", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _assign(db, cl, admin, admin)
    task = await _seed_task(db, cl, title="Set up chairs", is_completed=True)
    await db.commit()

    with patch(
        "app.routers.checklists.notify_checklist_item_status_changed",
        new_callable=AsyncMock,
    ) as mock_notify:
        async with client_as(admin) as c:
            resp = await c.patch(f"/api/checklists/{cl.id}/items/{task.id}/incomplete")
        assert resp.status_code == 200

    mock_notify.assert_called_once()
    _task, _cl, _actor, status_arg = mock_notify.call_args.args
    assert status_arg == "incomplete"
    assert _task.id == task.id
    assert _cl.id == cl.id
    assert _actor.id == admin.id


@pytest.mark.asyncio
async def test_telegram_failure_during_complete_does_not_rollback(db: AsyncSession, client_as):
    """A Telegram error in notify does not rollback the DB completion."""
    admin_role = _admin_role()
    db.add(admin_role)
    await db.flush()
    admin = await _seed_user(db, role=admin_role, username="admin_tgfail1", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _assign(db, cl, admin, admin)
    task = await _seed_task(db, cl, title="Clean room")
    await db.commit()

    async def _raise(*args, **kwargs):
        raise RuntimeError("Telegram is down")

    with patch("app.routers.checklists.notify_checklist_item_status_changed", side_effect=_raise):
        async with client_as(admin) as c:
            resp = await c.patch(
                f"/api/checklists/{cl.id}/items/{task.id}/complete",
                json={},
            )
        assert resp.status_code == 200

    # The DB state must be committed even though Telegram failed
    await db.refresh(task)
    assert task.is_completed is True
    assert task.completed_by_user_id == admin.id


@pytest.mark.asyncio
async def test_telegram_failure_during_incomplete_does_not_rollback(db: AsyncSession, client_as):
    """A Telegram error in notify does not rollback the DB incompletion."""
    admin_role = _admin_role()
    db.add(admin_role)
    await db.flush()
    admin = await _seed_user(db, role=admin_role, username="admin_tgfail2", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _assign(db, cl, admin, admin)
    task = await _seed_task(db, cl, title="Clean room", is_completed=True)
    await db.commit()

    async def _raise(*args, **kwargs):
        raise RuntimeError("Telegram is down")

    with patch("app.routers.checklists.notify_checklist_item_status_changed", side_effect=_raise):
        async with client_as(admin) as c:
            resp = await c.patch(f"/api/checklists/{cl.id}/items/{task.id}/incomplete")
        assert resp.status_code == 200

    await db.refresh(task)
    assert task.is_completed is False
    assert task.completed_by_user_id is None
    assert task.completed_at is None


@pytest.mark.asyncio
async def test_incomplete_clears_completion_fields(db: AsyncSession, client_as):
    """Incomplete endpoint zeroes out completed_at, completed_by_user_id, and completion_notes."""
    from datetime import datetime, timezone

    admin_role = _admin_role()
    db.add(admin_role)
    await db.flush()
    admin = await _seed_user(db, role=admin_role, username="admin_clear1", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _assign(db, cl, admin, admin)

    task = ChecklistItem(
        checklist_id=cl.id,
        title="Clean shelves",
        is_completed=True,
        completed_at=datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc),
        completed_by_user_id=admin.id,
        completion_notes="Looked great",
    )
    db.add(task)
    await db.commit()

    with patch(
        "app.routers.checklists.notify_checklist_item_status_changed",
        new_callable=AsyncMock,
    ):
        async with client_as(admin) as c:
            resp = await c.patch(f"/api/checklists/{cl.id}/items/{task.id}/incomplete")
        assert resp.status_code == 200

    await db.refresh(task)
    assert task.is_completed is False
    assert task.completed_at is None
    assert task.completed_by_user_id is None
    assert task.completion_notes is None


@pytest.mark.asyncio
async def test_cross_group_user_cannot_incomplete_other_groups_item(db: AsyncSession, client_as):
    """A user assigned to group2 cannot mark a group1 checklist item incomplete (403)."""
    admin_role = _admin_role()
    user_role = _user_role()
    db.add(admin_role)
    db.add(user_role)
    await db.flush()

    admin = await _seed_user(db, role=admin_role, username="admin_xg1", group_name=GroupName.GROUP_1)
    outsider = await _seed_user(db, role=user_role, username="user_xg2", group_name=GroupName.GROUP_2)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    # outsider is NOT assigned to this checklist
    task = await _seed_task(db, cl, title="Group 1 task", is_completed=True)
    await db.commit()

    with patch(
        "app.routers.checklists.notify_checklist_item_status_changed",
        new_callable=AsyncMock,
    ) as mock_notify:
        async with client_as(outsider) as c:
            resp = await c.patch(f"/api/checklists/{cl.id}/items/{task.id}/incomplete")
        assert resp.status_code == 403

    mock_notify.assert_not_called()


@pytest.mark.asyncio
async def test_auto_complete_does_not_call_status_changed_notification(db: AsyncSession):
    """
    auto_complete_return_task_for_transaction() must NOT trigger
    notify_checklist_item_status_changed — notifications for auto-return
    are handled by the return-proof flow, not the manual status-change helper.
    """
    from app.services.checklist_service import auto_complete_return_task_for_transaction

    admin_role = _admin_role()
    db.add(admin_role)
    await db.flush()
    admin = await _seed_user(db, role=admin_role, username="admin_auto1", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)

    # Fake transaction id — auto_complete looks it up by linked_transaction_id
    fake_txn_id = 9999
    task = ChecklistItem(
        checklist_id=cl.id,
        title="Return item XYZ",
        is_auto_generated=True,
        auto_type="ITEM_RETURN",
        linked_transaction_id=fake_txn_id,
        is_completed=False,
    )
    db.add(task)
    await db.commit()

    with patch(
        "app.routers.checklists.notify_checklist_item_status_changed",
        new_callable=AsyncMock,
    ) as mock_router_notify, patch(
        "app.services.telegram_service.notify_checklist_item_status_changed",
        new_callable=AsyncMock,
    ) as mock_service_notify:
        await auto_complete_return_task_for_transaction(db, fake_txn_id, admin.id)
        await db.commit()

    mock_router_notify.assert_not_called()
    mock_service_notify.assert_not_called()

    await db.refresh(task)
    assert task.is_completed is True


@pytest.mark.asyncio
async def test_no_op_complete_does_not_resend_notification(db: AsyncSession, client_as):
    """Re-completing an already-complete task does not fire a duplicate notification."""
    admin_role = _admin_role()
    db.add(admin_role)
    await db.flush()
    admin = await _seed_user(db, role=admin_role, username="admin_noop1", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _assign(db, cl, admin, admin)
    # Task already complete before the request
    task = await _seed_task(db, cl, title="Already done", is_completed=True)
    await db.commit()

    with patch(
        "app.routers.checklists.notify_checklist_item_status_changed",
        new_callable=AsyncMock,
    ) as mock_notify:
        async with client_as(admin) as c:
            resp = await c.patch(
                f"/api/checklists/{cl.id}/items/{task.id}/complete",
                json={},
            )
        assert resp.status_code == 200

    mock_notify.assert_not_called()


@pytest.mark.asyncio
async def test_no_op_incomplete_does_not_send_notification(db: AsyncSession, client_as):
    """Marking an already-incomplete task incomplete does not fire a notification."""
    admin_role = _admin_role()
    db.add(admin_role)
    await db.flush()
    admin = await _seed_user(db, role=admin_role, username="admin_noop2", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _assign(db, cl, admin, admin)
    # Task already incomplete
    task = await _seed_task(db, cl, title="Not done yet", is_completed=False)
    await db.commit()

    with patch(
        "app.routers.checklists.notify_checklist_item_status_changed",
        new_callable=AsyncMock,
    ) as mock_notify:
        async with client_as(admin) as c:
            resp = await c.patch(f"/api/checklists/{cl.id}/items/{task.id}/incomplete")
        assert resp.status_code == 200

    mock_notify.assert_not_called()


@pytest.mark.asyncio
async def test_cross_group_assigned_user_cannot_incomplete_foreign_checklist(db: AsyncSession, client_as):
    """A non-manager assigned to another group's checklist cannot mark items incomplete (403)."""
    admin_role = _admin_role()
    user_role = _user_role()
    db.add(admin_role)
    db.add(user_role)
    await db.flush()

    admin = await _seed_user(db, role=admin_role, username="admin_xg2", group_name=GroupName.GROUP_1)
    # outsider is in GROUP_2 but will be explicitly assigned to GROUP_1's checklist by admin
    outsider = await _seed_user(db, role=user_role, username="user_xg2b", group_name=GroupName.GROUP_2)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    # Admin assigns the cross-group user to the checklist
    await _assign(db, cl, outsider, admin)
    task = await _seed_task(db, cl, title="Group 1 task", is_completed=True)
    await db.commit()

    with patch(
        "app.routers.checklists.notify_checklist_item_status_changed",
        new_callable=AsyncMock,
    ) as mock_notify:
        async with client_as(outsider) as c:
            resp = await c.patch(f"/api/checklists/{cl.id}/items/{task.id}/incomplete")
        assert resp.status_code == 403

    mock_notify.assert_not_called()


# ── Issue 1: no-op complete preserves audit metadata ──────────────────────────

@pytest.mark.asyncio
async def test_no_op_complete_preserves_audit_metadata(db: AsyncSession, client_as):
    """Re-completing an already-complete task does not overwrite completed_at/by/notes."""
    from datetime import datetime, timezone

    admin_role = _admin_role()
    db.add(admin_role)
    await db.flush()
    original_completer = await _seed_user(db, role=admin_role, username="admin_orig1", group_name=GroupName.GROUP_1)
    second_completer = await _seed_user(db, role=admin_role, username="admin_second1", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _assign(db, cl, second_completer, original_completer)

    original_ts = datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc)
    task = ChecklistItem(
        checklist_id=cl.id,
        title="Already done task",
        is_completed=True,
        completed_at=original_ts,
        completed_by_user_id=original_completer.id,
        completion_notes="Original notes",
    )
    db.add(task)
    await db.commit()

    with patch(
        "app.routers.checklists.notify_checklist_item_status_changed",
        new_callable=AsyncMock,
    ) as mock_notify:
        async with client_as(second_completer) as c:
            resp = await c.patch(
                f"/api/checklists/{cl.id}/items/{task.id}/complete",
                json={"notes": "Overwritten notes"},
            )
        assert resp.status_code == 200

    mock_notify.assert_not_called()

    await db.refresh(task)
    # SQLite strips tzinfo; compare as naive UTC values
    assert task.completed_at.replace(tzinfo=None) == original_ts.replace(tzinfo=None)
    assert task.completed_by_user_id == original_completer.id
    assert task.completion_notes == "Original notes"


# ── Issue 2: cross-group complete symmetry ────────────────────────────────────

@pytest.mark.asyncio
async def test_cross_group_assigned_user_cannot_complete_foreign_checklist(db: AsyncSession, client_as):
    """A non-manager assigned to another group's checklist cannot complete its tasks (403)."""
    admin_role = _admin_role()
    user_role = _user_role()
    db.add(admin_role)
    db.add(user_role)
    await db.flush()

    admin = await _seed_user(db, role=admin_role, username="admin_xgc1", group_name=GroupName.GROUP_1)
    outsider = await _seed_user(db, role=user_role, username="user_xgc2", group_name=GroupName.GROUP_2)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    # Admin cross-assigns the GROUP_2 user to the GROUP_1 checklist
    await _assign(db, cl, outsider, admin)
    task = await _seed_task(db, cl, title="Group 1 manual task", is_completed=False)
    await db.commit()

    with patch(
        "app.routers.checklists.notify_checklist_item_status_changed",
        new_callable=AsyncMock,
    ) as mock_notify:
        async with client_as(outsider) as c:
            resp = await c.patch(
                f"/api/checklists/{cl.id}/items/{task.id}/complete",
                json={},
            )
        assert resp.status_code == 403

    mock_notify.assert_not_called()

    await db.refresh(task)
    assert task.is_completed is False


# ── Issue 3: service-level idempotency (concurrent-safe contract) ─────────────

@pytest.mark.asyncio
async def test_service_complete_is_idempotent(db: AsyncSession):
    """
    Calling complete_checklist_item twice returns (task, True) then (task, False).
    The second call must not overwrite the original completed_at/by/notes.
    """
    from datetime import datetime, timezone
    from app.services.checklist_service import complete_checklist_item

    admin_role = _admin_role()
    db.add(admin_role)
    await db.flush()
    user_a = await _seed_user(db, role=admin_role, username="svc_user_a", group_name=GroupName.GROUP_1)
    user_b = await _seed_user(db, role=admin_role, username="svc_user_b", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    task = await _seed_task(db, cl, title="Service idempotency task", is_completed=False)
    await db.commit()

    task1, t1 = await complete_checklist_item(db, item_id=task.id, user_id=user_a.id, notes="first notes")
    assert t1 is True
    assert task1.completed_by_user_id == user_a.id
    assert task1.completion_notes == "first notes"
    first_completed_at = task1.completed_at
    await db.commit()

    task2, t2 = await complete_checklist_item(db, item_id=task.id, user_id=user_b.id, notes="second notes")
    assert t2 is False
    assert task2.completed_by_user_id == user_a.id
    assert task2.completion_notes == "first notes"
    assert task2.completed_at == first_completed_at
    await db.commit()
