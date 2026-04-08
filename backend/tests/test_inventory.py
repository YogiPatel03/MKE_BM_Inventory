"""
Tests for cabinet, bin, and item CRUD endpoints.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.cabinet import Cabinet
from app.models.role import Role
from app.models.user import User


async def _seed_admin(db: AsyncSession) -> tuple[User, str]:
    role = Role(
        name="ADMIN",
        can_manage_inventory=True,
        can_manage_cabinets=True,
        can_manage_bins=True,
        can_manage_users=True,
        can_process_any_transaction=True,
        can_view_all_transactions=True,
        can_view_audit_logs=True,
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
    return user, role.id


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
    )
    db.add(role)
    await db.commit()
    return role


async def _login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    return r.json()["access_token"]


# ─── Cabinet tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_cabinet(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post("/api/cabinets", json={"name": "Cabinet A", "location": "Room 1"}, headers=headers)
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Cabinet A"
    assert data["location"] == "Room 1"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_cabinets(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post("/api/cabinets", json={"name": "A"}, headers=headers)
    await client.post("/api/cabinets", json={"name": "B"}, headers=headers)

    r = await client.get("/api/cabinets", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


@pytest.mark.asyncio
async def test_create_cabinet_requires_auth(client: AsyncClient, db: AsyncSession):
    r = await client.post("/api/cabinets", json={"name": "X"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_user_cannot_create_cabinet(client: AsyncClient, db: AsyncSession):
    user_role = await _seed_user_role(db)
    user = User(
        full_name="Bob",
        username="bob",
        password_hash=hash_password("bobpass1"),
        role_id=user_role.id,
    )
    db.add(user)
    await db.commit()

    token = await _login(client, "bob", "bobpass1")
    r = await client.post(
        "/api/cabinets",
        json={"name": "X"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_update_cabinet(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post("/api/cabinets", json={"name": "Old Name"}, headers=headers)
    cabinet_id = create.json()["id"]

    r = await client.patch(f"/api/cabinets/{cabinet_id}", json={"name": "New Name"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"


# ─── Bin tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_bin(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}

    cab = await client.post("/api/cabinets", json={"name": "Cab"}, headers=headers)
    cabinet_id = cab.json()["id"]

    r = await client.post(
        "/api/bins",
        json={"label": "A1", "cabinet_id": cabinet_id, "location_note": "Top shelf"},
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["label"] == "A1"
    assert r.json()["cabinet_id"] == cabinet_id


@pytest.mark.asyncio
async def test_list_bins_by_cabinet(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}

    cab1 = (await client.post("/api/cabinets", json={"name": "C1"}, headers=headers)).json()
    cab2 = (await client.post("/api/cabinets", json={"name": "C2"}, headers=headers)).json()

    await client.post("/api/bins", json={"label": "A1", "cabinet_id": cab1["id"]}, headers=headers)
    await client.post("/api/bins", json={"label": "B1", "cabinet_id": cab1["id"]}, headers=headers)
    await client.post("/api/bins", json={"label": "X1", "cabinet_id": cab2["id"]}, headers=headers)

    r = await client.get(f"/api/bins?cabinet_id={cab1['id']}", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


# ─── Item tests ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_item(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}

    cab = (await client.post("/api/cabinets", json={"name": "Cab"}, headers=headers)).json()

    r = await client.post(
        "/api/items",
        json={"name": "Hammer", "quantity_total": 5, "cabinet_id": cab["id"]},
        headers=headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Hammer"
    assert data["quantity_total"] == 5
    assert data["quantity_available"] == 5


@pytest.mark.asyncio
async def test_item_quantity_must_be_positive(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}

    cab = (await client.post("/api/cabinets", json={"name": "Cab"}, headers=headers)).json()

    r = await client.post(
        "/api/items",
        json={"name": "Hammer", "quantity_total": 0, "cabinet_id": cab["id"]},
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_update_item(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}

    cab = (await client.post("/api/cabinets", json={"name": "Cab"}, headers=headers)).json()
    item = (await client.post(
        "/api/items",
        json={"name": "Hammer", "quantity_total": 3, "cabinet_id": cab["id"]},
        headers=headers,
    )).json()

    r = await client.patch(f"/api/items/{item['id']}", json={"name": "Mallet"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Mallet"
