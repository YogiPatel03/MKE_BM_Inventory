"""
RBAC enforcement tests. Verifies that role boundaries are respected.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.cabinet import Cabinet
from app.models.item import Item
from app.models.role import Role
from app.models.user import User


def _make_role(name: str, **flags) -> Role:
    defaults = dict(
        can_manage_inventory=False,
        can_manage_cabinets=False,
        can_manage_bins=False,
        can_manage_users=False,
        can_process_any_transaction=False,
        can_view_all_transactions=False,
        can_view_audit_logs=False,
    )
    defaults.update(flags)
    return Role(name=name, **defaults)


async def _seed(db: AsyncSession):
    admin_role = _make_role(
        "ADMIN",
        can_manage_inventory=True, can_manage_cabinets=True, can_manage_bins=True,
        can_manage_users=True, can_process_any_transaction=True,
        can_view_all_transactions=True, can_view_audit_logs=True,
    )
    user_role = _make_role("USER")
    db.add(admin_role)
    db.add(user_role)
    await db.flush()

    admin = User(full_name="Admin", username="admin", password_hash=hash_password("adminpass"), role_id=admin_role.id)
    alice = User(full_name="Alice", username="alice", password_hash=hash_password("alicepass"), role_id=user_role.id)
    bob = User(full_name="Bob", username="bob", password_hash=hash_password("bobpass1"), role_id=user_role.id)
    db.add_all([admin, alice, bob])

    cabinet = Cabinet(name="Main Cabinet")
    db.add(cabinet)
    await db.flush()

    item = Item(name="Drill", quantity_total=2, quantity_available=2, cabinet_id=cabinet.id)
    db.add(item)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(alice)
    await db.refresh(bob)
    await db.refresh(item)
    return admin, alice, bob, item


async def _login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ─── User management ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_user_cannot_list_users(client: AsyncClient, db: AsyncSession):
    _, alice, _, _ = await _seed(db)
    token = await _login(client, "alice", "alicepass")
    r = await client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_list_users(client: AsyncClient, db: AsyncSession):
    await _seed(db)
    token = await _login(client, "admin", "adminpass")
    r = await client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert len(r.json()) >= 3


@pytest.mark.asyncio
async def test_user_cannot_create_user(client: AsyncClient, db: AsyncSession):
    _, _, _, _ = await _seed(db)
    token = await _login(client, "alice", "alicepass")
    r = await client.post(
        "/api/users",
        json={"full_name": "Dave", "username": "dave", "password": "password1", "role_id": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


# ─── Inventory management ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_user_cannot_create_cabinet(client: AsyncClient, db: AsyncSession):
    await _seed(db)
    token = await _login(client, "alice", "alicepass")
    r = await client.post(
        "/api/cabinets",
        json={"name": "Sneaky Cabinet"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_user_cannot_create_item(client: AsyncClient, db: AsyncSession):
    _, _, _, item = await _seed(db)
    token = await _login(client, "alice", "alicepass")
    r = await client.post(
        "/api/items",
        json={"name": "Sneaky Item", "quantity_total": 1, "cabinet_id": item.cabinet_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


# ─── Transaction permissions ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_user_can_checkout_for_self(client: AsyncClient, db: AsyncSession):
    _, alice, _, item = await _seed(db)
    token = await _login(client, "alice", "alicepass")
    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_user_cannot_checkout_for_other(client: AsyncClient, db: AsyncSession):
    _, alice, bob, item = await _seed(db)
    token = await _login(client, "alice", "alicepass")
    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": bob.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_checkout_for_other(client: AsyncClient, db: AsyncSession):
    _, _, bob, item = await _seed(db)
    token = await _login(client, "admin", "adminpass")
    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": bob.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_user_cannot_view_all_transactions(client: AsyncClient, db: AsyncSession):
    _, alice, bob, item = await _seed(db)

    # Bob checks out
    admin_token = await _login(client, "admin", "adminpass")
    await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": bob.id, "quantity": 1},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Alice should only see her own (none)
    alice_token = await _login(client, "alice", "alicepass")
    r = await client.get("/api/transactions", headers={"Authorization": f"Bearer {alice_token}"})
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_user_cannot_cancel_transaction(client: AsyncClient, db: AsyncSession):
    _, alice, _, item = await _seed(db)
    alice_token = await _login(client, "alice", "alicepass")

    checkout = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    tx_id = checkout.json()["id"]

    r = await client.post(
        f"/api/transactions/{tx_id}/cancel",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert r.status_code == 403
