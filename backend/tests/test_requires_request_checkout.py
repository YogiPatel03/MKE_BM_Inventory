"""
Tests for requires_request enforcement in the direct checkout flow.

Covers:
- Direct checkout allowed when requires_request=false (normal items unaffected)
- Direct checkout blocked for USER when requires_request=true (403)
- Error message mentions "request"
- No quantity change when blocked
- No transaction created when blocked
- COORDINATOR can bypass (201)
- ADMIN can bypass (201)
- GROUP_LEAD cannot bypass (403, uses request approval flow)
- Request flow still works for request-required items
- Bin full-checkout rule wins before item request rule (409 before 403)
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.bin import Bin
from app.models.cabinet import Cabinet
from app.models.item import Item
from app.models.role import Role
from app.models.room import Room
from app.models.transaction import Transaction
from app.models.user import User


# ─── Seed helpers ────────────────────────────────────────────────────────────

async def _seed_roles_and_users(db: AsyncSession):
    """
    Returns (admin, coordinator, group_lead, regular_user, item, cabinet).
    item has requires_request=False by default; tests set it as needed.
    """
    admin_role = Role(
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
    coord_role = Role(
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
    lead_role = Role(
        name="GROUP_LEAD",
        can_manage_inventory=False,
        can_manage_cabinets=False,
        can_manage_bins=False,
        can_manage_users=False,
        can_process_any_transaction=False,
        can_view_all_transactions=True,
        can_view_audit_logs=False,
        can_approve_requests=True,
    )
    user_role = Role(
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
    db.add_all([admin_role, coord_role, lead_role, user_role])
    await db.flush()

    admin = User(full_name="Admin", username="admin", password_hash=hash_password("adminpass"), role_id=admin_role.id)
    coord = User(full_name="Coord", username="coord", password_hash=hash_password("coordpass"), role_id=coord_role.id)
    lead = User(
        full_name="Lead", username="lead", password_hash=hash_password("leadpass"),
        role_id=lead_role.id, group_name="TeamA",
    )
    user = User(
        full_name="Alice", username="alice", password_hash=hash_password("alicepass"),
        role_id=user_role.id, group_name="TeamA",
    )
    db.add_all([admin, coord, lead, user])

    room = Room(name="Test Room")
    db.add(room)
    await db.flush()

    cabinet = Cabinet(name="Cabinet A", room_id=room.id)
    db.add(cabinet)
    await db.flush()

    item = Item(
        name="Power Drill",
        quantity_total=3,
        quantity_available=3,
        cabinet_id=cabinet.id,
        sku="RRD1",
    )
    db.add(item)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(coord)
    await db.refresh(lead)
    await db.refresh(user)
    await db.refresh(item)
    return admin, coord, lead, user, item, cabinet


async def _login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ─── Direct checkout with requires_request=False (no change expected) ─────────

@pytest.mark.asyncio
async def test_direct_checkout_allowed_when_requires_request_false(
    client: AsyncClient, db: AsyncSession
):
    _, _, _, user, item, _ = await _seed_roles_and_users(db)
    token = await _login(client, "alice", "alicepass")

    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": user.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201


# ─── Regular user blocked when requires_request=True ─────────────────────────

@pytest.mark.asyncio
async def test_direct_checkout_blocked_for_user_when_requires_request_true(
    client: AsyncClient, db: AsyncSession
):
    _, _, _, user, item, _ = await _seed_roles_and_users(db)
    item.requires_request = True
    await db.commit()

    token = await _login(client, "alice", "alicepass")
    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": user.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_error_message_mentions_request(client: AsyncClient, db: AsyncSession):
    _, _, _, user, item, _ = await _seed_roles_and_users(db)
    item.requires_request = True
    await db.commit()

    token = await _login(client, "alice", "alicepass")
    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": user.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
    assert "request" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_no_quantity_change_when_checkout_blocked(client: AsyncClient, db: AsyncSession):
    _, _, _, user, item, _ = await _seed_roles_and_users(db)
    item.requires_request = True
    await db.commit()
    original_qty = float(item.quantity_available)

    token = await _login(client, "alice", "alicepass")
    await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": user.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )

    await db.refresh(item)
    assert float(item.quantity_available) == original_qty


@pytest.mark.asyncio
async def test_no_transaction_created_when_checkout_blocked(client: AsyncClient, db: AsyncSession):
    _, _, _, user, item, _ = await _seed_roles_and_users(db)
    item.requires_request = True
    await db.commit()

    token = await _login(client, "alice", "alicepass")
    await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": user.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )

    result = await db.execute(select(Transaction).where(Transaction.item_id == item.id))
    assert result.scalar_one_or_none() is None


# ─── Coordinator bypass ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_coordinator_can_checkout_requires_request_item(
    client: AsyncClient, db: AsyncSession
):
    _, coord, _, user, item, _ = await _seed_roles_and_users(db)
    item.requires_request = True
    await db.commit()

    token = await _login(client, "coord", "coordpass")
    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": user.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201


# ─── Admin bypass ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_can_checkout_requires_request_item(client: AsyncClient, db: AsyncSession):
    admin, _, _, user, item, _ = await _seed_roles_and_users(db)
    item.requires_request = True
    await db.commit()

    token = await _login(client, "admin", "adminpass")
    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": user.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201


# ─── Group lead cannot bypass ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_group_lead_blocked_by_requires_request(client: AsyncClient, db: AsyncSession):
    """GROUP_LEAD has can_approve_requests but not can_process_any_transaction — no bypass."""
    _, _, lead, _, item, _ = await _seed_roles_and_users(db)
    item.requires_request = True
    await db.commit()

    token = await _login(client, "lead", "leadpass")
    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": lead.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


# ─── Request flow still works for request-required items ─────────────────────

@pytest.mark.asyncio
async def test_request_flow_works_for_requires_request_item(
    client: AsyncClient, db: AsyncSession
):
    """Regular user can submit a request; coordinator can approve it, creating a checkout."""
    _, coord, _, user, item, _ = await _seed_roles_and_users(db)
    item.requires_request = True
    await db.commit()

    user_token = await _login(client, "alice", "alicepass")
    submit = await client.post(
        "/api/requests",
        json={"item_id": item.id, "quantity_requested": 1, "reason": "Need for project"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert submit.status_code == 201
    req_id = submit.json()["id"]

    coord_token = await _login(client, "coord", "coordpass")
    approve = await client.post(
        f"/api/requests/{req_id}/approve",
        json={},
        headers={"Authorization": f"Bearer {coord_token}"},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "FULFILLED"

    # Verify checkout transaction was created and quantity decremented
    await db.refresh(item)
    assert float(item.quantity_available) == 2.0


# ─── Bin full-checkout rule wins before item request rule ────────────────────

@pytest.mark.asyncio
async def test_bin_full_checkout_rule_wins_before_requires_request(
    client: AsyncClient, db: AsyncSession
):
    """
    When a bin has requires_full_bin_checkout=True AND the item has requires_request=True,
    the bin constraint fires first (409 with 'full' or 'whole' in the message),
    not the request enforcement (403).
    """
    admin, _, _, user, _, cabinet = await _seed_roles_and_users(db)

    locked_bin = Bin(
        label="Locked Bin",
        bin_number="LCKB1",
        cabinet_id=cabinet.id,
        requires_full_bin_checkout=True,
    )
    db.add(locked_bin)
    await db.flush()

    bin_item = Item(
        name="Bin Drill",
        quantity_total=2,
        quantity_available=2,
        cabinet_id=cabinet.id,
        bin_id=locked_bin.id,
        sku="LCKD1",
        requires_request=True,
    )
    db.add(bin_item)
    await db.commit()
    await db.refresh(bin_item)

    # Admin has bypass for requires_request but bin rule blocks everyone from individual checkout
    admin_token = await _login(client, "admin", "adminpass")
    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": bin_item.id, "user_id": admin.id, "quantity": 1},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 409
    detail = r.json()["detail"].lower()
    assert "full" in detail or "whole" in detail

    # Regular user also gets the bin error (409), not the request error (403)
    user_token = await _login(client, "alice", "alicepass")
    r2 = await client.post(
        "/api/transactions/checkout",
        json={"item_id": bin_item.id, "user_id": user.id, "quantity": 1},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert r2.status_code == 409
    detail2 = r2.json()["detail"].lower()
    assert "full" in detail2 or "whole" in detail2
