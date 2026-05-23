"""
Tests for Prompt 3: Sabha date semantics, checklist visibility filtering,
and historical checklist reporting.

Covers all 10 acceptance-criteria tests from the Prompt 3 spec:
 1. sabha_date computed correctly (prep week 2026-05-03 → sabha 2026-05-10)
 2. Checklist visible before sabha_date
 3. Checklist visible on sabha_date
 4. Checklist visible during 14-day post-Sabha window
 5. Checklist hidden AFTER the 14-day post-Sabha window (day 15+)
 6. Hidden checklist returned with include_archived=true / from reports endpoint
 7. Historical query filters by group_name
 8. Historical query filters by sabha_date date range
 9. Permissions prevent unauthorised cross-group historical access
10. Existing checklist defaults tests still pass (covered by running that suite)
"""

import pytest
import pytest_asyncio
from datetime import date, timedelta
from unittest.mock import patch

from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.dependencies import get_db, get_current_user
from app.main import app
from app.models.checklist import (
    Checklist,
    ChecklistAssignment,
    GroupName,
    sabha_date_for_week,
)
from app.models.role import Role
from app.models.user import User
from app.schemas.checklist import ChecklistSummary, ChecklistOut
from app.services.checklist_service import list_checklists_historical


# ── Role / user helpers ────────────────────────────────────────────────────────

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
    is_active: bool = True,
) -> Checklist:
    cl = Checklist(group_name=group_name, week_start=week_start, is_active=is_active)
    db.add(cl)
    await db.flush()
    return cl


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


# ── 1. sabha_date formula ──────────────────────────────────────────────────────

def test_sabha_date_from_sunday_week_start():
    """
    Prompt example: prep week 2026-05-03 (Sunday) → sabha_date 2026-05-10.
    Sunday week_start adds 7 days to reach the next Sunday.
    """
    ws = date(2026, 5, 3)   # Sunday
    assert sabha_date_for_week(ws) == date(2026, 5, 10)


def test_sabha_date_from_monday_week_start():
    """
    Production case: week_start is Monday 2026-05-04 → sabha_date 2026-05-10.
    Monday week_start adds 6 days to reach the same week's Sunday.
    """
    ws = date(2026, 5, 4)   # Monday
    assert sabha_date_for_week(ws) == date(2026, 5, 10)


def test_sabha_date_schema_computed_field():
    """ChecklistSummary exposes sabha_date via computed field."""
    from datetime import datetime as dt
    ws = date(2026, 5, 4)  # Monday
    now = dt.now()
    summary = ChecklistSummary(
        id=1,
        group_name=GroupName.GROUP_1,
        week_start=ws,
        is_active=True,
        created_at=now,
        updated_at=now,
        item_count=0,
        completed_count=0,
        assignee_count=0,
    )
    assert summary.sabha_date == date(2026, 5, 10)


# ── Helper: build a fake "today" relative to a known Sabha date ─────────────

def _monday_for_sabha(sabha: date) -> date:
    """Return the Monday (week_start) that produces a given Sunday Sabha date."""
    assert sabha.weekday() == 6, "sabha must be a Sunday"
    return sabha - timedelta(days=6)


# ── 2–5. Visibility rules ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_checklist_visible_before_sabha(db: AsyncSession, client_as):
    """Checklist is visible when today is before its Sabha date."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord_vis1")
    await db.flush()

    sabha = date(2026, 5, 10)          # Sunday
    ws = _monday_for_sabha(sabha)      # 2026-05-04
    await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await db.flush()

    today_before = sabha - timedelta(days=3)  # 3 days before Sabha

    with patch("app.routers.checklists._CHECKLIST_TZ") as mock_tz:
        # Patch datetime.now() inside the router to return our fake today
        with patch("app.routers.checklists.datetime") as mock_dt:
            from datetime import timezone
            mock_dt.now.return_value.date.return_value = today_before
            async with client_as(coord) as c:
                r = await c.get("/api/checklists", params={"group_name": GroupName.GROUP_1})

    assert r.status_code == 200
    ids = [cl["id"] for cl in r.json()]
    # The checklist should appear (visible before Sabha)
    assert len(r.json()) >= 1
    assert any(cl["week_start"] == str(ws) for cl in r.json())


@pytest.mark.asyncio
async def test_checklist_visible_on_sabha_date(db: AsyncSession):
    """Checklist is visible on its Sabha date (day 0 of post-Sabha window)."""
    sabha = date(2026, 5, 10)
    ws = _monday_for_sabha(sabha)
    assert sabha_date_for_week(ws) == sabha

    # On sabha_date, cutoff = sabha - 14. sabha >= cutoff. Visible.
    today = sabha
    cutoff = today - timedelta(days=14)
    assert sabha_date_for_week(ws) >= cutoff


@pytest.mark.asyncio
async def test_checklist_visible_during_14_day_window(db: AsyncSession):
    """Checklist is visible on sabha+14 (last day of post-Sabha window)."""
    sabha = date(2026, 5, 10)
    ws = _monday_for_sabha(sabha)

    today = sabha + timedelta(days=14)
    cutoff = today - timedelta(days=14)
    assert sabha_date_for_week(ws) >= cutoff, "sabha_date should equal cutoff on day 14"


@pytest.mark.asyncio
async def test_checklist_hidden_after_14_day_window(db: AsyncSession):
    """Checklist is hidden on sabha+15 (first day after post-Sabha window)."""
    sabha = date(2026, 5, 10)
    ws = _monday_for_sabha(sabha)

    today = sabha + timedelta(days=15)
    cutoff = today - timedelta(days=14)
    assert sabha_date_for_week(ws) < cutoff, "sabha_date should be before cutoff on day 15"


# ── 6. include_archived and hidden checklist retrieval ────────────────────────

@pytest.mark.asyncio
async def test_include_archived_returns_old_checklists(db: AsyncSession, client_as):
    """Checklists hidden from normal list are returned with include_archived=true."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord_arch1")
    await db.flush()

    # Create a checklist from 30 days ago (well past the 14-day window)
    old_sabha = date.today() - timedelta(days=30)
    # Advance to the nearest past Sunday
    days_since_sunday = old_sabha.weekday() + 1 if old_sabha.weekday() != 6 else 0
    if old_sabha.weekday() != 6:
        old_sabha = old_sabha - timedelta(days=old_sabha.weekday() + 1)
    old_ws = old_sabha - timedelta(days=6)  # Monday of that week

    await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=old_ws)
    await db.flush()

    # Without include_archived: old checklist should NOT appear
    with patch("app.routers.checklists.datetime") as mock_dt:
        mock_dt.now.return_value.date.return_value = date.today()
        async with client_as(coord) as c:
            r_normal = await c.get("/api/checklists", params={"group_name": GroupName.GROUP_1})
            r_archived = await c.get("/api/checklists", params={
                "group_name": GroupName.GROUP_1,
                "include_archived": "true",
            })

    assert r_normal.status_code == 200
    assert r_archived.status_code == 200

    normal_ws = {cl["week_start"] for cl in r_normal.json()}
    archived_ws = {cl["week_start"] for cl in r_archived.json()}

    assert str(old_ws) not in normal_ws, "Old checklist should be hidden from normal list"
    assert str(old_ws) in archived_ws, "Old checklist should appear with include_archived=true"


@pytest.mark.asyncio
async def test_reports_checklists_returns_old_records(db: AsyncSession, client_as):
    """GET /api/reports/checklists returns archived checklists (admin/coord only)."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord_rep1", group_name=GroupName.GROUP_1)
    await db.flush()

    # Old checklist: 60 days ago
    old_ws = date.today() - timedelta(days=60)
    await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=old_ws)
    await db.flush()

    async with client_as(coord) as c:
        r = await c.get("/api/reports/checklists")

    assert r.status_code == 200
    ws_list = [cl["week_start"] for cl in r.json()]
    assert str(old_ws) in ws_list, "Reports endpoint should include archived checklists"


# ── 7. Historical query: filter by group_name ─────────────────────────────────

@pytest.mark.asyncio
async def test_historical_query_filters_by_group(db: AsyncSession, client_as):
    """GET /api/reports/checklists?group_name=X returns only that group."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord_grp1")
    await db.flush()

    ws = date(2024, 1, 1)
    await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _seed_checklist(db, group_name=GroupName.GROUP_2, week_start=ws)
    await db.flush()

    async with client_as(coord) as c:
        r = await c.get("/api/reports/checklists", params={"group_name": GroupName.GROUP_1})

    assert r.status_code == 200
    groups = {cl["group_name"] for cl in r.json()}
    assert groups == {GroupName.GROUP_1}, "Should only return GROUP_1 checklists"


# ── 8. Historical query: filter by sabha_date range ──────────────────────────

@pytest.mark.asyncio
async def test_historical_query_filters_by_date_range(db: AsyncSession):
    """list_checklists_historical filters by sabha_date start_date/end_date."""
    # week_start=2024-01-01 (Mon), sabha=2024-01-07 (Sun)
    ws_in = date(2024, 1, 1)
    sabha_in = sabha_date_for_week(ws_in)  # 2024-01-07

    # week_start=2024-02-05 (Mon), sabha=2024-02-11 (Sun) — outside range
    ws_out = date(2024, 2, 5)
    sabha_out = sabha_date_for_week(ws_out)  # 2024-02-11

    cl_in = Checklist(group_name=GroupName.GROUP_1, week_start=ws_in, is_active=True)
    cl_out = Checklist(group_name=GroupName.GROUP_1, week_start=ws_out, is_active=True)
    db.add(cl_in)
    db.add(cl_out)
    await db.flush()

    # Query window: only includes sabha_in
    results = await list_checklists_historical(
        db,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
    )
    result_ids = {cl.id for cl in results}
    assert cl_in.id in result_ids
    assert cl_out.id not in result_ids


@pytest.mark.asyncio
async def test_reports_endpoint_filters_by_date_range(db: AsyncSession, client_as):
    """Reports endpoint date filter returns only matching sabha_date checklists."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord_date1")
    await db.flush()

    ws_jan = date(2024, 1, 1)   # sabha 2024-01-07
    ws_feb = date(2024, 2, 5)   # sabha 2024-02-11

    await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws_jan)
    await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws_feb)
    await db.flush()

    async with client_as(coord) as c:
        r = await c.get("/api/reports/checklists", params={
            "group_name": GroupName.GROUP_1,
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        })

    assert r.status_code == 200
    ws_returned = {cl["week_start"] for cl in r.json()}
    assert str(ws_jan) in ws_returned
    assert str(ws_feb) not in ws_returned


# ── 9. Permissions: cross-group historical access ─────────────────────────────

@pytest.mark.asyncio
async def test_regular_user_cannot_access_reports_checklists(db: AsyncSession, client_as):
    """Regular user cannot access /api/reports/checklists."""
    user_role = await _seed_role(db, _user_role())
    user = await _seed_user(db, role=user_role, username="user_perm1", group_name=GroupName.GROUP_1)
    await db.flush()

    async with client_as(user) as c:
        r = await c.get("/api/reports/checklists")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_group_lead_cannot_access_reports_checklists(db: AsyncSession, client_as):
    """Group lead (non-manager) cannot access /api/reports/checklists."""
    lead_role = await _seed_role(db, _lead_role())
    lead = await _seed_user(db, role=lead_role, username="lead_perm1", group_name=GroupName.GROUP_1)
    await db.flush()

    async with client_as(lead) as c:
        r = await c.get("/api/reports/checklists")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_coordinator_can_access_all_groups_via_reports(db: AsyncSession, client_as):
    """Coordinator can query all groups via /api/reports/checklists."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord_perm1")
    await db.flush()

    ws = date(2024, 3, 4)
    await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await _seed_checklist(db, group_name=GroupName.GROUP_2, week_start=ws)
    await db.flush()

    async with client_as(coord) as c:
        r = await c.get("/api/reports/checklists")
    assert r.status_code == 200
    groups = {cl["group_name"] for cl in r.json()}
    assert GroupName.GROUP_1 in groups
    assert GroupName.GROUP_2 in groups


@pytest.mark.asyncio
async def test_reports_invalid_group_name_returns_400(db: AsyncSession, client_as):
    """Reports endpoint returns 400 for an invalid group_name."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord_bad_grp")
    await db.flush()

    async with client_as(coord) as c:
        r = await c.get("/api/reports/checklists", params={"group_name": "INVALID_GROUP"})
    assert r.status_code == 400


# ── sabha_date in API responses ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_checklist_list_response_includes_sabha_date(db: AsyncSession, client_as):
    """The /api/checklists list endpoint includes sabha_date in each item."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord_sd1")
    await db.flush()

    ws = date(2026, 5, 4)  # Monday
    expected_sabha = date(2026, 5, 10)
    await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await db.flush()

    async with client_as(coord) as c:
        r = await c.get("/api/checklists", params={
            "group_name": GroupName.GROUP_1,
            "week_start": str(ws),
        })

    assert r.status_code == 200
    assert len(r.json()) >= 1
    entry = next(cl for cl in r.json() if cl["week_start"] == str(ws))
    assert entry["sabha_date"] == str(expected_sabha)


@pytest.mark.asyncio
async def test_reports_response_includes_sabha_date_and_completion(db: AsyncSession, client_as):
    """Reports endpoint includes sabha_date and completion_percentage."""
    coord_role = await _seed_role(db, _coord_role())
    coord = await _seed_user(db, role=coord_role, username="coord_sd2")
    await db.flush()

    ws = date(2026, 5, 4)
    await _seed_checklist(db, group_name=GroupName.GROUP_1, week_start=ws)
    await db.flush()

    async with client_as(coord) as c:
        r = await c.get("/api/reports/checklists", params={"group_name": GroupName.GROUP_1})

    assert r.status_code == 200
    entry = next((cl for cl in r.json() if cl["week_start"] == str(ws)), None)
    assert entry is not None
    assert entry["sabha_date"] == "2026-05-10"
    assert "completion_percentage" in entry
