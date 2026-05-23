"""
Tests for recurring checklist assignment defaults (Prompt 2).

Validates:
1. Default assignee is copied to a newly-created weekly checklist.
2. Removing a user from one week does not remove them from recurring defaults.
3. Re-running get_or_create_weekly_checklists does not re-add a manually removed user.
4. Adding/removing recurring defaults via service and API.
5. Duplicate active default is rejected cleanly.
6. Group lead cannot manage another group's defaults.
7. Regular user cannot manage defaults.
8. Admin/coordinator can manage defaults.
"""

import pytest
import pytest_asyncio
from datetime import date, timedelta
from unittest.mock import patch

from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.dependencies import get_db
from app.main import app
from app.models.checklist import (
    Checklist,
    ChecklistAssignment,
    ChecklistAssignmentDefault,
    GroupName,
)
from app.models.role import Role
from app.models.user import User
from app.services.checklist_service import (
    add_checklist_default,
    copy_active_defaults_to_checklist,
    get_or_create_weekly_checklists,
    list_checklist_defaults,
)


# ── Role helpers ───────────────────────────────────────────────────────────────

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


def _coord_role() -> Role:
    return Role(
        name="COORDINATOR",
        can_manage_inventory=True,
        can_manage_cabinets=True,
        can_manage_bins=True,
        can_manage_users=False,
        can_process_any_transaction=True,
        can_view_all_transactions=True,
        can_view_audit_logs=False,
        can_approve_requests=True,
    )


def _lead_role() -> Role:
    return Role(
        name="GROUP_LEAD",
        can_manage_inventory=False,
        can_manage_cabinets=False,
        can_manage_bins=False,
        can_manage_users=False,
        can_process_any_transaction=True,
        can_view_all_transactions=False,
        can_view_audit_logs=False,
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


# ── Seed helpers ───────────────────────────────────────────────────────────────

async def _seed_role(db: AsyncSession, role: Role) -> Role:
    db.add(role)
    await db.flush()
    return role


async def _seed_user(
    db: AsyncSession,
    *,
    role: Role,
    username: str,
    full_name: str = "Test User",
    group_name: str | None = None,
) -> User:
    user = User(
        full_name=full_name,
        username=username,
        password_hash=hash_password("pass"),
        role_id=role.id,
        group_name=group_name,
    )
    db.add(user)
    await db.flush()
    return user


async def _seed_default(
    db: AsyncSession,
    *,
    group_name: str,
    user: User,
    assigned_by: User,
    is_active: bool = True,
) -> ChecklistAssignmentDefault:
    d = ChecklistAssignmentDefault(
        group_name=group_name,
        user_id=user.id,
        assigned_by_id=assigned_by.id,
        is_active=is_active,
    )
    db.add(d)
    await db.flush()
    return d


def _this_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


# ── Client fixture with auth override ─────────────────────────────────────────

@pytest_asyncio.fixture
async def client_as(db):
    """
    Returns a factory: client_as(user) → AsyncClient that authenticates as that user.
    The db session is shared so ORM objects from seed helpers are visible.
    """
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    from app.dependencies import get_current_user

    def make_client(user: User):
        app.dependency_overrides[get_current_user] = lambda: user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield make_client

    app.dependency_overrides.clear()


# ── Service-level tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_copy_defaults_to_new_checklist(db: AsyncSession):
    """Default assignee is copied when a new weekly checklist is created."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord1")
    user_role = await _seed_role(db, _user_role())
    member = await _seed_user(db, role=user_role, username="member1", group_name=GroupName.GROUP_1)

    await _seed_default(db, group_name=GroupName.GROUP_1, user=member, assigned_by=coord)
    await db.flush()

    monday = _this_monday()
    checklist = Checklist(group_name=GroupName.GROUP_1, week_start=monday, is_active=True)
    db.add(checklist)
    await db.flush()

    count = await copy_active_defaults_to_checklist(db, checklist)
    assert count == 1

    assignments = (await db.execute(
        select(ChecklistAssignment).where(ChecklistAssignment.checklist_id == checklist.id)
    )).scalars().all()
    assert len(assignments) == 1
    assert assignments[0].user_id == member.id
    assert assignments[0].assigned_by_id == coord.id


@pytest.mark.asyncio
async def test_weekly_override_does_not_modify_defaults(db: AsyncSession):
    """Removing a user from one week's ChecklistAssignment doesn't touch recurring defaults."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord2")
    user_role = await _seed_role(db, _user_role())
    member = await _seed_user(db, role=user_role, username="member2", group_name=GroupName.GROUP_1)

    default = await _seed_default(db, group_name=GroupName.GROUP_1, user=member, assigned_by=coord)

    monday = _this_monday()
    checklist = Checklist(group_name=GroupName.GROUP_1, week_start=monday, is_active=True)
    db.add(checklist)
    await db.flush()

    # Simulate copying defaults, then manually removing the assignment this week
    await copy_active_defaults_to_checklist(db, checklist)

    assignment = (await db.execute(
        select(ChecklistAssignment).where(
            ChecklistAssignment.checklist_id == checklist.id,
            ChecklistAssignment.user_id == member.id,
        )
    )).scalar_one_or_none()
    assert assignment is not None

    # Weekly override: remove the assignment
    await db.delete(assignment)
    await db.flush()

    # Recurring default must still be active
    refreshed = (await db.execute(
        select(ChecklistAssignmentDefault).where(ChecklistAssignmentDefault.id == default.id)
    )).scalar_one()
    assert refreshed.is_active is True


@pytest.mark.asyncio
async def test_rerun_generation_does_not_readd_removed_user(db: AsyncSession):
    """Re-running get_or_create_weekly_checklists for an existing checklist does not re-add removed user."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord3", group_name=GroupName.GROUP_1)
    user_role = await _seed_role(db, _user_role())
    member = await _seed_user(db, role=user_role, username="member3", group_name=GroupName.GROUP_1)

    await _seed_default(db, group_name=GroupName.GROUP_1, user=member, assigned_by=coord)

    monday = _this_monday()
    # Pre-create the checklist (simulating first generation)
    checklist = Checklist(group_name=GroupName.GROUP_1, week_start=monday, is_active=True)
    db.add(checklist)
    await db.flush()
    await copy_active_defaults_to_checklist(db, checklist)

    # Coordinator removes member from this week's checklist
    assignment = (await db.execute(
        select(ChecklistAssignment).where(
            ChecklistAssignment.checklist_id == checklist.id,
            ChecklistAssignment.user_id == member.id,
        )
    )).scalar_one_or_none()
    assert assignment is not None
    await db.delete(assignment)
    await db.flush()

    # Simulate re-running get_or_create_weekly_checklists (checklist already exists)
    with patch("app.services.checklist_service._current_week_monday", return_value=monday):
        await get_or_create_weekly_checklists(db)

    # Member must NOT be re-added
    reassigned = (await db.execute(
        select(ChecklistAssignment).where(
            ChecklistAssignment.checklist_id == checklist.id,
            ChecklistAssignment.user_id == member.id,
        )
    )).scalar_one_or_none()
    assert reassigned is None, "Re-running generation must not re-add manually removed users"


@pytest.mark.asyncio
async def test_add_checklist_default_service(db: AsyncSession):
    """add_checklist_default creates an active default row."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord4")
    user_role = await _seed_role(db, _user_role())
    member = await _seed_user(db, role=user_role, username="member4", group_name=GroupName.GROUP_2)

    default = await add_checklist_default(db, GroupName.GROUP_2, member.id, coord.id)

    assert default.id is not None
    assert default.group_name == GroupName.GROUP_2
    assert default.user_id == member.id
    assert default.assigned_by_id == coord.id
    assert default.is_active is True


@pytest.mark.asyncio
async def test_duplicate_active_default_rejected(db: AsyncSession):
    """Adding the same user twice to the same group's defaults raises a conflict error."""
    from app.core.exceptions import TransactionConflictError

    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord5")
    user_role = await _seed_role(db, _user_role())
    member = await _seed_user(db, role=user_role, username="member5", group_name=GroupName.GROUP_1)

    await add_checklist_default(db, GroupName.GROUP_1, member.id, coord.id)

    with pytest.raises(TransactionConflictError):
        await add_checklist_default(db, GroupName.GROUP_1, member.id, coord.id)


@pytest.mark.asyncio
async def test_inactive_default_allows_re_add(db: AsyncSession):
    """A previously deactivated default can be re-added (inserts a new active row)."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord6")
    user_role = await _seed_role(db, _user_role())
    member = await _seed_user(db, role=user_role, username="member6", group_name=GroupName.GROUP_1)

    # Add then deactivate
    default = await add_checklist_default(db, GroupName.GROUP_1, member.id, coord.id)
    default.is_active = False
    await db.flush()

    # Re-add — should not conflict
    new_default = await add_checklist_default(db, GroupName.GROUP_1, member.id, coord.id)
    assert new_default.id != default.id
    assert new_default.is_active is True


@pytest.mark.asyncio
async def test_list_checklist_defaults(db: AsyncSession):
    """list_checklist_defaults returns only active defaults for the specified group."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord7")
    user_role = await _seed_role(db, _user_role())
    m1 = await _seed_user(db, role=user_role, username="m7a", group_name=GroupName.GROUP_1)
    m2 = await _seed_user(db, role=user_role, username="m7b", group_name=GroupName.GROUP_2)

    await _seed_default(db, group_name=GroupName.GROUP_1, user=m1, assigned_by=coord)
    await _seed_default(db, group_name=GroupName.GROUP_2, user=m2, assigned_by=coord)
    # Inactive row for GROUP_1 — should be excluded
    await _seed_default(db, group_name=GroupName.GROUP_1, user=m2, assigned_by=coord, is_active=False)

    defaults = await list_checklist_defaults(db, GroupName.GROUP_1)
    assert len(defaults) == 1
    assert defaults[0].user_id == m1.id


# ── API-level tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_can_manage_any_group_defaults(db: AsyncSession, client_as):
    """Admin can list, add, and remove defaults for any group."""
    admin_role = await _seed_role(db, _admin_role())
    admin = await _seed_user(db, role=admin_role, username="admin8", group_name=GroupName.GROUP_1)
    user_role = await _seed_role(db, _user_role())
    member = await _seed_user(db, role=user_role, username="member8", group_name=GroupName.GROUP_2)
    await db.flush()

    async with client_as(admin) as c:
        # List defaults for a different group
        r = await c.get("/api/checklists/defaults", params={"group_name": GroupName.GROUP_2})
        assert r.status_code == 200
        assert r.json() == []

        # Add default for another group
        r = await c.post("/api/checklists/defaults", json={"group_name": GroupName.GROUP_2, "user_id": member.id})
        assert r.status_code == 201
        default_id = r.json()["id"]

        # Remove it
        r = await c.delete(f"/api/checklists/defaults/{default_id}")
        assert r.status_code == 204

        # Confirm deactivated
        r = await c.get("/api/checklists/defaults", params={"group_name": GroupName.GROUP_2})
        assert r.status_code == 200
        assert r.json() == []


@pytest.mark.asyncio
async def test_coordinator_can_manage_any_group_defaults(db: AsyncSession, client_as):
    """Coordinator can manage defaults for any group."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord9", group_name=GroupName.GROUP_1)
    user_role = await _seed_role(db, _user_role())
    member = await _seed_user(db, role=user_role, username="member9", group_name=GroupName.GROUP_3)
    await db.flush()

    async with client_as(coord) as c:
        r = await c.post("/api/checklists/defaults", json={"group_name": GroupName.GROUP_3, "user_id": member.id})
        assert r.status_code == 201


@pytest.mark.asyncio
async def test_group_lead_can_manage_own_group_defaults(db: AsyncSession, client_as):
    """Group lead can manage defaults for their own group."""
    lead_role = await _seed_role(db, _lead_role())
    lead = await _seed_user(db, role=lead_role, username="lead10", group_name=GroupName.GROUP_1)
    user_role = await _seed_role(db, _user_role())
    member = await _seed_user(db, role=user_role, username="member10", group_name=GroupName.GROUP_1)
    await db.flush()

    async with client_as(lead) as c:
        r = await c.post("/api/checklists/defaults", json={"group_name": GroupName.GROUP_1, "user_id": member.id})
        assert r.status_code == 201

        default_id = r.json()["id"]
        r = await c.delete(f"/api/checklists/defaults/{default_id}")
        assert r.status_code == 204


@pytest.mark.asyncio
async def test_group_lead_cannot_manage_other_group_defaults(db: AsyncSession, client_as):
    """Group lead is forbidden from managing defaults for a different group."""
    lead_role = await _seed_role(db, _lead_role())
    lead = await _seed_user(db, role=lead_role, username="lead11", group_name=GroupName.GROUP_1)
    user_role = await _seed_role(db, _user_role())
    member = await _seed_user(db, role=user_role, username="member11", group_name=GroupName.GROUP_2)
    await db.flush()

    async with client_as(lead) as c:
        r = await c.post("/api/checklists/defaults", json={"group_name": GroupName.GROUP_2, "user_id": member.id})
        assert r.status_code == 403

        r = await c.get("/api/checklists/defaults", params={"group_name": GroupName.GROUP_2})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_regular_user_cannot_manage_defaults(db: AsyncSession, client_as):
    """Regular user cannot access defaults endpoints."""
    user_role = await _seed_role(db, _user_role())
    user = await _seed_user(db, role=user_role, username="user12", group_name=GroupName.GROUP_1)
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord12")
    member = await _seed_user(db, role=user_role, username="member12", group_name=GroupName.GROUP_1)
    await db.flush()

    async with client_as(user) as c:
        # Even their own group
        r = await c.post("/api/checklists/defaults", json={"group_name": GroupName.GROUP_1, "user_id": member.id})
        assert r.status_code == 403

        r = await c.get("/api/checklists/defaults", params={"group_name": GroupName.GROUP_1})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_api_duplicate_default_returns_409(db: AsyncSession, client_as):
    """Posting the same default twice returns 409 Conflict."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord13")
    user_role = await _seed_role(db, _user_role())
    member = await _seed_user(db, role=user_role, username="member13", group_name=GroupName.GROUP_1)
    await db.flush()

    async with client_as(coord) as c:
        r = await c.post("/api/checklists/defaults", json={"group_name": GroupName.GROUP_1, "user_id": member.id})
        assert r.status_code == 201

        r = await c.post("/api/checklists/defaults", json={"group_name": GroupName.GROUP_1, "user_id": member.id})
        assert r.status_code == 409


@pytest.mark.asyncio
async def test_new_checklist_generation_copies_defaults(db: AsyncSession):
    """get_or_create_weekly_checklists copies active defaults into newly-created checklists."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord14")
    user_role = await _seed_role(db, _user_role())
    member = await _seed_user(db, role=user_role, username="member14", group_name=GroupName.GROUP_1)

    await _seed_default(db, group_name=GroupName.GROUP_1, user=member, assigned_by=coord)
    await db.flush()

    monday = _this_monday()
    with patch("app.services.checklist_service._current_week_monday", return_value=monday):
        checklists = await get_or_create_weekly_checklists(db)

    group1_cl = next(cl for cl in checklists if cl.group_name == GroupName.GROUP_1)

    assignments = (await db.execute(
        select(ChecklistAssignment).where(ChecklistAssignment.checklist_id == group1_cl.id)
    )).scalars().all()

    assert any(a.user_id == member.id for a in assignments), "Default should be copied to new checklist"


@pytest.mark.asyncio
async def test_delete_default_returns_404_for_nonexistent(db: AsyncSession, client_as):
    """Deleting a non-existent default returns 404."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord15")
    await db.flush()

    async with client_as(coord) as c:
        r = await c.delete("/api/checklists/defaults/99999")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_add_default_for_nonexistent_user_returns_404(db: AsyncSession, client_as):
    """Adding a default for a non-existent user returns 404."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord16")
    await db.flush()

    async with client_as(coord) as c:
        r = await c.post("/api/checklists/defaults", json={"group_name": GroupName.GROUP_1, "user_id": 99999})
        assert r.status_code == 404


# ── Issue 1: Group lead cross-group default authorization ─────────────────────

@pytest.mark.asyncio
async def test_group_lead_cannot_add_cross_group_user_to_own_defaults(db: AsyncSession, client_as):
    """Group lead of GROUP_1 cannot add a GROUP_2 user to GROUP_1's recurring defaults."""
    lead_role = await _seed_role(db, _lead_role())
    lead = await _seed_user(db, role=lead_role, username="lead17", group_name=GroupName.GROUP_1)
    user_role = await _seed_role(db, _user_role())
    # Target user is in GROUP_2 — not the same group as the default being created
    outsider = await _seed_user(db, role=user_role, username="outsider17", group_name=GroupName.GROUP_2)
    await db.flush()

    async with client_as(lead) as c:
        r = await c.post(
            "/api/checklists/defaults",
            json={"group_name": GroupName.GROUP_1, "user_id": outsider.id},
        )
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_group_lead_can_add_same_group_user_to_own_defaults(db: AsyncSession, client_as):
    """Group lead of GROUP_1 can add a GROUP_1 user to GROUP_1's recurring defaults."""
    lead_role = await _seed_role(db, _lead_role())
    lead = await _seed_user(db, role=lead_role, username="lead18", group_name=GroupName.GROUP_1)
    user_role = await _seed_role(db, _user_role())
    member = await _seed_user(db, role=user_role, username="member18", group_name=GroupName.GROUP_1)
    await db.flush()

    async with client_as(lead) as c:
        r = await c.post(
            "/api/checklists/defaults",
            json={"group_name": GroupName.GROUP_1, "user_id": member.id},
        )
        assert r.status_code == 201


@pytest.mark.asyncio
async def test_admin_can_add_cross_group_user_to_defaults(db: AsyncSession, client_as):
    """Admin can add a user from any group to any group's recurring defaults."""
    admin_role = await _seed_role(db, _admin_role())
    admin = await _seed_user(db, role=admin_role, username="admin19", group_name=GroupName.GROUP_1)
    user_role = await _seed_role(db, _user_role())
    outsider = await _seed_user(db, role=user_role, username="outsider19", group_name=GroupName.GROUP_2)
    await db.flush()

    async with client_as(admin) as c:
        r = await c.post(
            "/api/checklists/defaults",
            json={"group_name": GroupName.GROUP_1, "user_id": outsider.id},
        )
        assert r.status_code == 201


@pytest.mark.asyncio
async def test_coordinator_can_add_cross_group_user_to_defaults(db: AsyncSession, client_as):
    """Coordinator can add a user from any group to any group's recurring defaults."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord20", group_name=GroupName.GROUP_1)
    user_role = await _seed_role(db, _user_role())
    outsider = await _seed_user(db, role=user_role, username="outsider20", group_name=GroupName.GROUP_3)
    await db.flush()

    async with client_as(coord) as c:
        r = await c.post(
            "/api/checklists/defaults",
            json={"group_name": GroupName.GROUP_1, "user_id": outsider.id},
        )
        assert r.status_code == 201
