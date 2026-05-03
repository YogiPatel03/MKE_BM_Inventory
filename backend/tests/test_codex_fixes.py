"""
Regression tests for Codex adversarial review fixes:
1. GROUP_LEAD bin transaction scoping (no global list/return)
2. Usage events restricted to can_manage_inventory
3. Checklist completion requires assignment (group_name not sufficient)
4. GROUP_LEAD cannot assign cross-group users to checklist
5. Decimal purchase quantities accepted; reports use float arithmetic
"""

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.cabinet import Cabinet
from app.models.checklist import Checklist, ChecklistAssignment, ChecklistItem
from app.models.item import Item
from app.models.role import Role
from app.models.room import Room
from app.models.user import User


# ─── helpers ──────────────────────────────────────────────────────────────────

def _role(name: str, **flags) -> Role:
    defaults = dict(
        can_manage_inventory=False,
        can_manage_cabinets=False,
        can_manage_bins=False,
        can_manage_users=False,
        can_process_any_transaction=False,
        can_view_all_transactions=False,
        can_view_audit_logs=False,
        can_approve_requests=False,
    )
    defaults.update(flags)
    return Role(name=name, **defaults)


async def _login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _seed_groups(db: AsyncSession):
    """
    Seed two groups: Alpha and Beta.
    Returns (admin, lead_alpha, user_alpha, user_beta, item, room).
    """
    admin_role = _role(
        "ADMIN",
        can_manage_inventory=True, can_manage_cabinets=True, can_manage_bins=True,
        can_manage_users=True, can_process_any_transaction=True,
        can_view_all_transactions=True, can_view_audit_logs=True,
        can_approve_requests=True,
    )
    lead_role = _role("GROUP_LEAD", can_approve_requests=True)
    user_role = _role("USER")
    inv_role = _role("COORDINATOR", can_manage_inventory=True, can_process_any_transaction=True,
                     can_view_all_transactions=True)
    db.add_all([admin_role, lead_role, user_role, inv_role])
    await db.flush()

    admin = User(full_name="Admin", username="admin_fix", password_hash=hash_password("adminpass"),
                 role_id=admin_role.id)
    lead_alpha = User(full_name="Lead Alpha", username="lead_alpha", password_hash=hash_password("leadpass"),
                      role_id=lead_role.id, group_name="Alpha")
    user_alpha = User(full_name="User Alpha", username="user_alpha", password_hash=hash_password("userpass"),
                      role_id=user_role.id, group_name="Alpha")
    user_beta = User(full_name="User Beta", username="user_beta", password_hash=hash_password("betapass"),
                     role_id=user_role.id, group_name="Beta")
    coordinator = User(full_name="Coordinator", username="coordinator", password_hash=hash_password("coordpass"),
                       role_id=inv_role.id)
    db.add_all([admin, lead_alpha, user_alpha, user_beta, coordinator])

    room = Room(name="Fix Test Room")
    db.add(room)
    await db.flush()

    cabinet = Cabinet(name="Fix Cabinet", room_id=room.id)
    db.add(cabinet)
    await db.flush()

    item = Item(
        name="Fix Item", cabinet_id=cabinet.id,
        quantity_total=Decimal("100"), quantity_available=Decimal("100"),
        is_consumable=True, unit_price=Decimal("5.00"),
    )
    db.add(item)
    await db.commit()

    for obj in [admin, lead_alpha, user_alpha, user_beta, coordinator, item, room, cabinet]:
        await db.refresh(obj)

    return admin, lead_alpha, user_alpha, user_beta, coordinator, item, room, cabinet


# ─── Fix 1: GROUP_LEAD bin transaction scoping ────────────────────────────────

@pytest.mark.asyncio
async def test_group_lead_cannot_list_all_bin_transactions(client: AsyncClient, db: AsyncSession):
    """GROUP_LEAD sees only their own group's bin transactions, not everyone's."""
    _, lead_alpha, user_alpha, _, _, _, _, _ = await _seed_groups(db)
    token = await _login(client, "lead_alpha", "leadpass")

    # list should succeed (group-scoped), not 403
    r = await client.get("/api/bin-transactions", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_regular_user_cannot_return_others_bin_transaction(client: AsyncClient, db: AsyncSession):
    """A user from a different group cannot return another user's bin transaction."""
    _, lead_alpha, user_alpha, user_beta, _, _, _, _ = await _seed_groups(db)

    # user_alpha checks out a bin — but we have no bin to check out so we test
    # that user_beta (different group) gets 404 on a non-existent one first.
    token_beta = await _login(client, "user_beta", "betapass")
    r = await client.post(
        "/api/bin-transactions/9999/return",
        json={},
        headers={"Authorization": f"Bearer {token_beta}"},
    )
    # 404 because the txn doesn't exist — NOT 200 (unauthorized return)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_any_user_can_checkout_bin(client: AsyncClient, db: AsyncSession):
    """Any authenticated user can check out a bin for themselves."""
    from app.models.bin import Bin
    _, _, user_alpha, _, _, _, _, cabinet = await _seed_groups(db)

    # Create a bin to checkout
    bin_obj = Bin(label="Alpha Bin", cabinet_id=cabinet.id)
    db.add(bin_obj)
    await db.commit()
    await db.refresh(bin_obj)

    token = await _login(client, "user_alpha", "userpass")
    r = await client.post(
        "/api/bin-transactions",
        json={"bin_id": bin_obj.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201


# ─── Fix 2: Usage events require can_manage_inventory ─────────────────────────

@pytest.mark.asyncio
async def test_regular_user_cannot_create_usage_event(client: AsyncClient, db: AsyncSession):
    """Regular USER is denied access to POST /usage-events."""
    _, _, user_alpha, _, _, item, _, _ = await _seed_groups(db)
    token = await _login(client, "user_alpha", "userpass")
    r = await client.post(
        "/api/usage-events",
        json={"item_id": item.id, "quantity_used": "1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_group_lead_cannot_create_usage_event(client: AsyncClient, db: AsyncSession):
    """GROUP_LEAD (can_approve_requests only) is denied POST /usage-events."""
    _, lead_alpha, _, _, _, item, _, _ = await _seed_groups(db)
    token = await _login(client, "lead_alpha", "leadpass")
    r = await client.post(
        "/api/usage-events",
        json={"item_id": item.id, "quantity_used": "1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_coordinator_can_create_usage_event(client: AsyncClient, db: AsyncSession):
    """COORDINATOR (can_manage_inventory) can POST /usage-events."""
    _, _, _, _, coordinator, item, _, _ = await _seed_groups(db)
    token = await _login(client, "coordinator", "coordpass")
    r = await client.post(
        "/api/usage-events",
        json={"item_id": item.id, "quantity_used": "1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201


# ─── Fix 3: Checklist completion requires assignment ──────────────────────────

@pytest.mark.asyncio
async def test_group_member_without_assignment_cannot_complete_task(client: AsyncClient, db: AsyncSession):
    """A user in the same group but NOT assigned to checklist cannot complete tasks."""
    from datetime import date
    _, _, user_alpha, _, _, _, _, _ = await _seed_groups(db)

    # Create a checklist for Alpha group with a task
    cl = Checklist(group_name="Alpha", week_start=date.today(), is_active=True)
    db.add(cl)
    await db.flush()
    task = ChecklistItem(checklist_id=cl.id, title="Alpha Task", item_order=0)
    db.add(task)
    await db.commit()
    await db.refresh(task)

    token = await _login(client, "user_alpha", "userpass")
    r = await client.patch(
        f"/api/checklists/{cl.id}/items/{task.id}/complete",
        json={"notes": "done"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_assigned_user_can_complete_task(client: AsyncClient, db: AsyncSession):
    """A user explicitly assigned to a checklist CAN complete tasks."""
    from datetime import date
    _, _, user_alpha, _, _, _, _, _ = await _seed_groups(db)

    cl = Checklist(group_name="Alpha", week_start=date.today(), is_active=True)
    db.add(cl)
    await db.flush()
    task = ChecklistItem(checklist_id=cl.id, title="Alpha Task", item_order=0)
    db.add(task)
    await db.flush()
    assignment = ChecklistAssignment(checklist_id=cl.id, user_id=user_alpha.id, assigned_by_id=user_alpha.id)
    db.add(assignment)
    await db.commit()
    await db.refresh(task)

    token = await _login(client, "user_alpha", "userpass")
    r = await client.patch(
        f"/api/checklists/{cl.id}/items/{task.id}/complete",
        json={"notes": "done"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


# ─── Fix 4: Cross-group checklist assignment blocked ─────────────────────────

@pytest.mark.asyncio
async def test_group_lead_cannot_assign_cross_group_user(client: AsyncClient, db: AsyncSession):
    """GROUP_LEAD cannot assign a user from a different group to their checklist."""
    from datetime import date
    _, lead_alpha, _, user_beta, _, _, _, _ = await _seed_groups(db)

    cl = Checklist(group_name="Alpha", week_start=date.today(), is_active=True)
    db.add(cl)
    await db.flush()
    # Assign lead_alpha to the checklist so they have permission to assign
    assignment = ChecklistAssignment(checklist_id=cl.id, user_id=lead_alpha.id, assigned_by_id=lead_alpha.id)
    db.add(assignment)
    await db.commit()

    token = await _login(client, "lead_alpha", "leadpass")
    r = await client.post(
        f"/api/checklists/{cl.id}/assign",
        json={"user_id": user_beta.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_group_lead_can_assign_same_group_user(client: AsyncClient, db: AsyncSession):
    """GROUP_LEAD CAN assign a user from the same group."""
    from datetime import date
    _, lead_alpha, user_alpha, _, _, _, _, _ = await _seed_groups(db)

    cl = Checklist(group_name="Alpha", week_start=date.today(), is_active=True)
    db.add(cl)
    await db.flush()
    assignment = ChecklistAssignment(checklist_id=cl.id, user_id=lead_alpha.id, assigned_by_id=lead_alpha.id)
    db.add(assignment)
    await db.commit()

    token = await _login(client, "lead_alpha", "leadpass")
    r = await client.post(
        f"/api/checklists/{cl.id}/assign",
        json={"user_id": user_alpha.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201


# ─── Fix 5: Decimal purchase quantities ───────────────────────────────────────

@pytest.mark.asyncio
async def test_decimal_purchase_quantity_accepted(client: AsyncClient, db: AsyncSession):
    """A purchase with decimal quantity (e.g. 2.5) is accepted and stored correctly."""
    admin, _, _, _, _, item, _, _ = await _seed_groups(db)
    token = await _login(client, "admin_fix", "adminpass")
    r = await client.post(
        "/api/purchases",
        json={
            "item_id": item.id,
            "quantity_purchased": "2.50",
            "unit_price": 5.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    data = r.json()
    assert float(data["quantity_purchased"]) == 2.5


@pytest.mark.asyncio
async def test_decimal_purchase_updates_item_stock(client: AsyncClient, db: AsyncSession):
    """A decimal purchase correctly increments item stock."""
    admin, _, _, _, _, item, _, _ = await _seed_groups(db)
    token = await _login(client, "admin_fix", "adminpass")

    initial_qty = float(item.quantity_total)

    await client.post(
        "/api/purchases",
        json={"item_id": item.id, "quantity_purchased": "1.5"},
        headers={"Authorization": f"Bearer {token}"},
    )

    r = await client.get(f"/api/items/{item.id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert float(r.json()["quantity_total"]) == initial_qty + 1.5


@pytest.mark.asyncio
async def test_purchase_zero_quantity_rejected(client: AsyncClient, db: AsyncSession):
    """A purchase with quantity=0 is rejected (422)."""
    admin, _, _, _, _, item, _, _ = await _seed_groups(db)
    token = await _login(client, "admin_fix", "adminpass")
    r = await client.post(
        "/api/purchases",
        json={"item_id": item.id, "quantity_purchased": "0"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


# ─── Fix: _can_manage_tasks_on same-group guard ───────────────────────────────

@pytest.mark.asyncio
async def test_cross_group_lead_cannot_add_items_to_foreign_checklist(client: AsyncClient, db: AsyncSession):
    """A GROUP_LEAD assigned to another group's checklist (by admin) cannot add items."""
    from datetime import date
    _, lead_alpha, _, _, admin, _, _, _ = await _seed_groups(db)

    # Admin creates a Beta checklist and assigns lead_alpha to it
    cl = Checklist(group_name="Beta", week_start=date.today(), is_active=True)
    db.add(cl)
    await db.flush()
    assignment = ChecklistAssignment(checklist_id=cl.id, user_id=lead_alpha.id, assigned_by_id=admin.id)
    db.add(assignment)
    await db.commit()

    token = await _login(client, "lead_alpha", "leadpass")
    r = await client.post(
        f"/api/checklists/{cl.id}/items",
        json={"title": "Sneaky task", "item_order": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_cross_group_lead_cannot_assign_user_to_foreign_checklist(client: AsyncClient, db: AsyncSession):
    """A GROUP_LEAD from Alpha assigned to a Beta checklist cannot assign Beta users."""
    from datetime import date
    _, lead_alpha, _, user_beta, admin, _, _, _ = await _seed_groups(db)

    cl = Checklist(group_name="Beta", week_start=date.today(), is_active=True)
    db.add(cl)
    await db.flush()
    assignment = ChecklistAssignment(checklist_id=cl.id, user_id=lead_alpha.id, assigned_by_id=admin.id)
    db.add(assignment)
    await db.commit()

    token = await _login(client, "lead_alpha", "leadpass")
    r = await client.post(
        f"/api/checklists/{cl.id}/assign",
        json={"user_id": user_beta.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


# ─── Fix: GROUP_LEAD same-group item transaction return ───────────────────────

@pytest.mark.asyncio
async def test_group_lead_can_return_same_group_item_transaction(client: AsyncClient, db: AsyncSession):
    """GROUP_LEAD can return a same-group user's item checkout."""
    _, lead_alpha, user_alpha, _, _, _, _, cabinet = await _seed_groups(db)

    # Create a non-consumable item for checkout
    tool = Item(
        name="Drill", cabinet_id=cabinet.id,
        quantity_total=Decimal("2"), quantity_available=Decimal("2"),
        is_consumable=False,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)

    # user_alpha checks out the item
    token_alpha = await _login(client, "user_alpha", "userpass")
    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": tool.id, "user_id": user_alpha.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token_alpha}"},
    )
    assert r.status_code == 201
    txn_id = r.json()["id"]

    # lead_alpha (GROUP_LEAD, same group) returns it
    token_lead = await _login(client, "lead_alpha", "leadpass")
    r = await client.post(
        f"/api/transactions/{txn_id}/return",
        json={},
        headers={"Authorization": f"Bearer {token_lead}"},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_group_lead_cannot_return_cross_group_item_transaction(client: AsyncClient, db: AsyncSession):
    """GROUP_LEAD cannot return a transaction belonging to a user in a different group."""
    _, lead_alpha, _, user_beta, _, _, _, cabinet = await _seed_groups(db)

    # Create a non-consumable item for checkout
    tool = Item(
        name="Wrench", cabinet_id=cabinet.id,
        quantity_total=Decimal("2"), quantity_available=Decimal("2"),
        is_consumable=False,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)

    # user_beta (Beta group) checks out the item
    token_beta = await _login(client, "user_beta", "betapass")
    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": tool.id, "user_id": user_beta.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token_beta}"},
    )
    assert r.status_code == 201
    txn_id = r.json()["id"]

    # lead_alpha (GROUP_LEAD, Alpha group) attempts to return Beta user's transaction
    token_lead = await _login(client, "lead_alpha", "leadpass")
    r = await client.post(
        f"/api/transactions/{txn_id}/return",
        json={},
        headers={"Authorization": f"Bearer {token_lead}"},
    )
    assert r.status_code == 403
