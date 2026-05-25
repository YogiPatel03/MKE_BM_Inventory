"""
Tests for PATCH /api/checklists/{checklist_id}/items/{item_id}
(update_checklist_item endpoint).

Covers:
1. Normal/manual task — title and description can be updated (200).
2. Weekly-default-style task (is_auto_generated=False) — still editable (200).
3. Explicit assignee_id: null clears the per-task assignee back to Everyone (200).
4. Auto-generated ITEM_RETURN task cannot be edited — returns 409.
5. Auto-generated BIN_RETURN task cannot be edited — returns 409.
6. Regression: DELETE on an auto-generated task still returns 409.
7. Regression: completing an auto-generated ITEM_RETURN task still works (200).
"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

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


# ─── Seed helpers ──────────────────────────────────────────────────────────────

async def _seed_role(db: AsyncSession, role: Role) -> Role:
    db.add(role)
    await db.flush()
    return role


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
    description: str | None = None,
    assignee_id: int | None = None,
    is_auto_generated: bool = False,
    auto_type: str | None = None,
    is_completed: bool = False,
) -> ChecklistItem:
    task = ChecklistItem(
        checklist_id=checklist.id,
        title=title,
        description=description,
        assignee_id=assignee_id,
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
async def test_manual_task_can_be_edited(db: AsyncSession, client_as):
    """A normal manually-created checklist task can have its title and description updated."""
    admin_role = await _seed_role(db, _admin_role())
    admin = await _seed_user(db, role=admin_role, username="admin_edit1", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _assign(db, cl, admin, admin)
    task = await _seed_task(db, cl, title="Original title", description="Original desc")
    await db.commit()

    async with client_as(admin) as c:
        resp = await c.patch(
            f"/api/checklists/{cl.id}/items/{task.id}",
            json={"title": "Updated title", "description": "Updated desc"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Updated title"
    assert data["description"] == "Updated desc"


@pytest.mark.asyncio
async def test_weekly_default_style_task_can_be_edited(db: AsyncSession, client_as):
    """A task with is_auto_generated=False (e.g. a standard Pre/Post-Sabha weekly task)
    is NOT blocked by the return-task guard and can be freely edited."""
    admin_role = await _seed_role(db, _admin_role())
    admin = await _seed_user(db, role=admin_role, username="admin_wk1", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _assign(db, cl, admin, admin)
    # is_auto_generated=False / auto_type=None — the same flags as weekly Pre/Post-Sabha tasks.
    task = await _seed_task(
        db, cl,
        title="Set up chairs",
        is_auto_generated=False,
        auto_type=None,
    )
    await db.commit()

    async with client_as(admin) as c:
        resp = await c.patch(
            f"/api/checklists/{cl.id}/items/{task.id}",
            json={"title": "Set up chairs and tables"},
        )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Set up chairs and tables"


@pytest.mark.asyncio
async def test_explicit_null_assignee_clears_to_everyone(db: AsyncSession, client_as):
    """Sending assignee_id: null (explicit) clears the per-task assignee back to Everyone (null).
    This verifies the model_fields_set fix that distinguishes 'not sent' from 'sent as null'."""
    admin_role = await _seed_role(db, _admin_role())
    admin = await _seed_user(db, role=admin_role, username="admin_null1", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _assign(db, cl, admin, admin)
    # Task starts with admin as the specific per-task assignee
    task = await _seed_task(db, cl, title="Assigned task", assignee_id=admin.id)
    await db.commit()

    async with client_as(admin) as c:
        resp = await c.patch(
            f"/api/checklists/{cl.id}/items/{task.id}",
            json={"assignee_id": None},  # explicit JSON null → should clear
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["assignee_id"] is None
    assert data["assignee"] is None


@pytest.mark.asyncio
async def test_patch_assignee_to_valid_assigned_user(db: AsyncSession, client_as):
    """PATCH normal task with assignee_id set to a valid assigned user → 200.
    Response includes correct assignee_id, assignee.full_name, and assignee.username."""
    admin_role = await _seed_role(db, _admin_role())
    admin = await _seed_user(db, role=admin_role, username="admin_asgn1", group_name=GroupName.GROUP_1)

    # A second user who is assigned to the checklist
    from app.models.role import Role as _Role
    member_role = _Role(
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
    db.add(member_role)
    await db.flush()
    member = User(
        full_name="Jane Member",
        username="jane_member",
        password_hash=hash_password("pass"),
        role_id=member_role.id,
        group_name=GroupName.GROUP_1,
    )
    db.add(member)
    await db.flush()

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _assign(db, cl, admin, admin)
    await _assign(db, cl, member, admin)  # member is assigned to the checklist
    task = await _seed_task(db, cl, title="Unassigned task")  # starts as Everyone
    await db.commit()

    async with client_as(admin) as c:
        resp = await c.patch(
            f"/api/checklists/{cl.id}/items/{task.id}",
            json={"assignee_id": member.id},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["assignee_id"] == member.id
    assert data["assignee"]["full_name"] == "Jane Member"
    assert data["assignee"]["username"] == "jane_member"


@pytest.mark.asyncio
async def test_item_return_task_cannot_be_edited(db: AsyncSession, client_as):
    """An auto-generated ITEM_RETURN task is rejected with 409 Conflict."""
    admin_role = await _seed_role(db, _admin_role())
    admin = await _seed_user(db, role=admin_role, username="admin_ret1", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _assign(db, cl, admin, admin)
    task = await _seed_task(
        db, cl,
        title="Return: Drill ×1",
        is_auto_generated=True,
        auto_type="ITEM_RETURN",
    )
    await db.commit()

    async with client_as(admin) as c:
        resp = await c.patch(
            f"/api/checklists/{cl.id}/items/{task.id}",
            json={"title": "Tampered title"},
        )
    assert resp.status_code == 409
    assert "auto-generated return tasks cannot be edited" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_bin_return_task_cannot_be_edited(db: AsyncSession, client_as):
    """An auto-generated BIN_RETURN task is rejected with 409 Conflict."""
    admin_role = await _seed_role(db, _admin_role())
    admin = await _seed_user(db, role=admin_role, username="admin_bin1", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _assign(db, cl, admin, admin)
    task = await _seed_task(
        db, cl,
        title="Return: Storage Bin #3",
        is_auto_generated=True,
        auto_type="BIN_RETURN",
    )
    await db.commit()

    async with client_as(admin) as c:
        resp = await c.patch(
            f"/api/checklists/{cl.id}/items/{task.id}",
            json={"title": "Tampered title"},
        )
    assert resp.status_code == 409
    assert "auto-generated return tasks cannot be edited" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_auto_generated_still_returns_409(db: AsyncSession, client_as):
    """Regression: the existing DELETE guard on auto-generated tasks still returns 409."""
    admin_role = await _seed_role(db, _admin_role())
    admin = await _seed_user(db, role=admin_role, username="admin_del1", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _assign(db, cl, admin, admin)
    task = await _seed_task(
        db, cl,
        title="Return: Ladder ×1",
        is_auto_generated=True,
        auto_type="ITEM_RETURN",
    )
    await db.commit()

    async with client_as(admin) as c:
        resp = await c.delete(f"/api/checklists/{cl.id}/items/{task.id}")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_complete_auto_generated_return_task_still_blocked(db: AsyncSession, client_as):
    """Regression: the /complete endpoint still blocks manual completion of ITEM_RETURN tasks
    (returns 409 — you must use the return flow). The edit guard must not change this."""
    admin_role = await _seed_role(db, _admin_role())
    admin = await _seed_user(db, role=admin_role, username="admin_cmp1", group_name=GroupName.GROUP_1)

    ws = date(2026, 5, 4)
    cl = await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _assign(db, cl, admin, admin)
    task = await _seed_task(
        db, cl,
        title="Return: Projector ×1",
        is_auto_generated=True,
        auto_type="ITEM_RETURN",
        is_completed=False,
    )
    await db.commit()

    async with client_as(admin) as c:
        resp = await c.patch(
            f"/api/checklists/{cl.id}/items/{task.id}/complete",
            json={},
        )
    # The complete endpoint intentionally rejects this — the item must be returned
    # through the checkout return flow, which calls auto_complete_return_task_for_transaction.
    assert resp.status_code == 409
