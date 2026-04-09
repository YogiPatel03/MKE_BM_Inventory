"""
Tests for consumable item usage, stock adjustments, bin move consistency,
bin checkout restrictions, and request approval fulfillment.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.cabinet import Cabinet
from app.models.bin import Bin
from app.models.role import Role
from app.models.user import User


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _seed_admin(db: AsyncSession):
    role = Role(
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
    db.add(role)
    await db.flush()
    user = User(
        full_name="Admin",
        username="admin",
        password_hash=hash_password("adminpass"),
        role_id=role.id,
    )
    db.add(user)
    await db.commit()
    return user, role


async def _seed_user_role(db: AsyncSession) -> Role:
    role = Role(
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
    db.add(role)
    await db.commit()
    return role


async def _login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


async def _setup(client: AsyncClient, db: AsyncSession, headers: dict):
    """Create cabinet, bin, consumable item, non-consumable item. Returns ids."""
    cab = (await client.post("/api/cabinets", json={"name": "Cabinet A"}, headers=headers)).json()
    bin_ = (await client.post("/api/bins", json={"label": "B1", "cabinet_id": cab["id"]}, headers=headers)).json()
    consumable = (await client.post(
        "/api/items",
        json={"name": "Paper", "quantity_total": 100, "cabinet_id": cab["id"], "is_consumable": True, "unit_price": 0.20},
        headers=headers,
    )).json()
    standard = (await client.post(
        "/api/items",
        json={"name": "Hammer", "quantity_total": 3, "cabinet_id": cab["id"], "is_consumable": False},
        headers=headers,
    )).json()
    return cab, bin_, consumable, standard


# ─── Consumable usage ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_consumable_as_used(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    _, _, consumable, _ = await _setup(client, db, headers)

    r = await client.post(
        "/api/usage-events",
        json={"item_id": consumable["id"], "quantity_used": 10, "notes": "Event setup"},
        headers=headers,
    )
    assert r.status_code == 201

    # Verify stock reduced permanently
    item_r = (await client.get(f"/api/items/{consumable['id']}", headers=headers)).json()
    assert item_r["quantity_available"] == 90
    assert item_r["quantity_total"] == 90  # total also reduces for consumables


@pytest.mark.asyncio
async def test_mark_non_consumable_as_used_rejected(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    _, _, _, standard = await _setup(client, db, headers)

    r = await client.post(
        "/api/usage-events",
        json={"item_id": standard["id"], "quantity_used": 1},
        headers=headers,
    )
    assert r.status_code == 409  # TransactionConflictError


@pytest.mark.asyncio
async def test_usage_history_endpoint(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    _, _, consumable, _ = await _setup(client, db, headers)

    await client.post(
        "/api/usage-events",
        json={"item_id": consumable["id"], "quantity_used": 5},
        headers=headers,
    )
    r = await client.get(f"/api/usage-events/item/{consumable['id']}", headers=headers)
    assert r.status_code == 200
    events = r.json()
    assert len(events) == 1
    assert events[0]["quantity_used"] == 5


# ─── Checkout restricted for consumables ─────────────────────────────────────

@pytest.mark.asyncio
async def test_checkout_consumable_rejected(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    _, _, consumable, _ = await _setup(client, db, headers)

    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": consumable["id"], "user_id": 1, "quantity": 1},
        headers=headers,
    )
    assert r.status_code == 409  # TransactionConflictError


# ─── Bin checkout restriction ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cannot_individually_checkout_bin_item(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}

    cab = (await client.post("/api/cabinets", json={"name": "C"}, headers=headers)).json()
    bin_ = (await client.post("/api/bins", json={"label": "B1", "cabinet_id": cab["id"]}, headers=headers)).json()
    item = (await client.post(
        "/api/items",
        json={"name": "Widget", "quantity_total": 5, "cabinet_id": cab["id"], "bin_id": bin_["id"]},
        headers=headers,
    )).json()

    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item["id"], "user_id": 1, "quantity": 1},
        headers=headers,
    )
    assert r.status_code == 409  # must reject individual checkout of bin item


# ─── Stock adjustment ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stock_adjustment_add(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    _, _, _, standard = await _setup(client, db, headers)

    r = await client.post(
        "/api/stock-adjustments",
        json={"item_id": standard["id"], "delta": 10, "reason": "RESTOCK", "notes": "New delivery"},
        headers=headers,
    )
    assert r.status_code == 201

    item_r = (await client.get(f"/api/items/{standard['id']}", headers=headers)).json()
    assert item_r["quantity_total"] == 13
    assert item_r["quantity_available"] == 13


@pytest.mark.asyncio
async def test_stock_adjustment_negative_below_zero_rejected(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    _, _, _, standard = await _setup(client, db, headers)

    r = await client.post(
        "/api/stock-adjustments",
        json={"item_id": standard["id"], "delta": -999, "reason": "CORRECTION"},
        headers=headers,
    )
    assert r.status_code == 409  # TransactionConflictError


# ─── Bin move consistency ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_move_bin_cascades_to_items(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}

    cab_a = (await client.post("/api/cabinets", json={"name": "A"}, headers=headers)).json()
    cab_b = (await client.post("/api/cabinets", json={"name": "B"}, headers=headers)).json()
    bin_ = (await client.post("/api/bins", json={"label": "B1", "cabinet_id": cab_a["id"]}, headers=headers)).json()
    item = (await client.post(
        "/api/items",
        json={"name": "Widget", "quantity_total": 2, "cabinet_id": cab_a["id"], "bin_id": bin_["id"]},
        headers=headers,
    )).json()

    assert item["cabinet_id"] == cab_a["id"]

    r = await client.post(
        "/api/moves/bin",
        json={"bin_id": bin_["id"], "to_cabinet_id": cab_b["id"], "notes": "Reorganizing"},
        headers=headers,
    )
    assert r.status_code == 201

    # Item should now point to cabinet B
    updated_item = (await client.get(f"/api/items/{item['id']}", headers=headers)).json()
    assert updated_item["cabinet_id"] == cab_b["id"]


# ─── Request approval fulfillment ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_request_creates_transaction(client: AsyncClient, db: AsyncSession):
    _, admin_role = await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}

    cab = (await client.post("/api/cabinets", json={"name": "C"}, headers=headers)).json()
    item = (await client.post(
        "/api/items",
        json={"name": "Tape", "quantity_total": 10, "cabinet_id": cab["id"]},
        headers=headers,
    )).json()

    # Create request
    req = (await client.post(
        "/api/requests",
        json={"item_id": item["id"], "quantity_requested": 3, "reason": "Need for event"},
        headers=headers,
    )).json()
    assert req["status"] == "PENDING"

    # Approve → should fulfill immediately
    approved = (await client.post(f"/api/requests/{req['id']}/approve", json={}, headers=headers)).json()
    assert approved["status"] == "FULFILLED"
    assert approved["fulfilled_at"] is not None

    # Item stock should have decreased
    updated_item = (await client.get(f"/api/items/{item['id']}", headers=headers)).json()
    assert updated_item["quantity_available"] == 7  # 10 - 3


@pytest.mark.asyncio
async def test_approve_request_insufficient_stock(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}

    cab = (await client.post("/api/cabinets", json={"name": "C"}, headers=headers)).json()
    item = (await client.post(
        "/api/items",
        json={"name": "Tape", "quantity_total": 2, "cabinet_id": cab["id"]},
        headers=headers,
    )).json()

    req = (await client.post(
        "/api/requests",
        json={"item_id": item["id"], "quantity_requested": 5},
        headers=headers,
    )).json()

    r = await client.post(f"/api/requests/{req['id']}/approve", json={}, headers=headers)
    assert r.status_code in (400, 409)
