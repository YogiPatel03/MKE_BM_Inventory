"""
Tests for cabinet, bin, and item CRUD endpoints.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bin import Bin
from app.core.security import hash_password
from app.models.cabinet import Cabinet
from app.models.item import Item
from app.models.role import Role
from app.models.room import Room
from app.models.user import User


async def _make_room(db: AsyncSession, name: str = "Test Room") -> Room:
    room = Room(name=name)
    db.add(room)
    await db.flush()
    return room


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
    room = await _make_room(db)

    r = await client.post("/api/cabinets", json={"name": "Cabinet A", "location": "Room 1", "room_id": room.id}, headers=headers)
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
    room = await _make_room(db)

    await client.post("/api/cabinets", json={"name": "A", "room_id": room.id}, headers=headers)
    await client.post("/api/cabinets", json={"name": "B", "room_id": room.id}, headers=headers)

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
        json={"name": "X", "room_id": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_update_cabinet(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)

    create = await client.post("/api/cabinets", json={"name": "Old Name", "room_id": room.id}, headers=headers)
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
    room = await _make_room(db)

    cab = await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)
    cabinet_id = cab.json()["id"]

    r = await client.post(
        "/api/bins",
        json={
            "label": "A1",
            "bin_number": "TCA1",
            "cabinet_id": cabinet_id,
            "location_note": "Top shelf",
        },
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["label"] == "A1"
    assert r.json()["bin_number"] == "TCA1"
    assert r.json()["cabinet_id"] == cabinet_id


@pytest.mark.asyncio
async def test_create_bin_requires_bin_number(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    missing = await client.post(
        "/api/bins",
        json={"label": "Glue Bin", "cabinet_id": cab["id"]},
        headers=headers,
    )
    assert missing.status_code == 422

    blank = await client.post(
        "/api/bins",
        json={"label": "Glue Bin", "bin_number": "   ", "cabinet_id": cab["id"]},
        headers=headers,
    )
    assert blank.status_code == 422


@pytest.mark.asyncio
async def test_update_bin_number(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()
    bin_ = (await client.post(
        "/api/bins",
        json={"label": "Glue Bin", "bin_number": "TCD1", "cabinet_id": cab["id"]},
        headers=headers,
    )).json()

    r = await client.patch(f"/api/bins/{bin_['id']}", json={"bin_number": "TCD2"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["bin_number"] == "TCD2"


@pytest.mark.asyncio
async def test_duplicate_bin_number_returns_conflict(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    first = await client.post(
        "/api/bins",
        json={"label": "Glue Bin", "bin_number": "TCD1", "cabinet_id": cab["id"]},
        headers=headers,
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/bins",
        json={"label": "Tape Bin", "bin_number": "TCD1", "cabinet_id": cab["id"]},
        headers=headers,
    )
    assert second.status_code == 409
    assert "TCD1" in second.json()["detail"]


@pytest.mark.asyncio
async def test_duplicate_bin_number_case_insensitive_returns_conflict(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    first = await client.post(
        "/api/bins",
        json={"label": "Glue Bin", "bin_number": "SMCD1", "cabinet_id": cab["id"]},
        headers=headers,
    )
    assert first.status_code == 201
    assert first.json()["bin_number"] == "SMCD1"
    second = await client.post(
        "/api/bins",
        json={"label": "Tape Bin", "bin_number": "smcd1", "cabinet_id": cab["id"]},
        headers=headers,
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_update_bin_number_case_insensitive_duplicate_returns_conflict(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    first = (await client.post(
        "/api/bins",
        json={"label": "Glue Bin", "bin_number": "SMCD1", "cabinet_id": cab["id"]},
        headers=headers,
    )).json()
    second = (await client.post(
        "/api/bins",
        json={"label": "Tape Bin", "bin_number": "SMCD2", "cabinet_id": cab["id"]},
        headers=headers,
    )).json()

    r = await client.patch(f"/api/bins/{second['id']}", json={"bin_number": "smcd1"}, headers=headers)
    assert r.status_code == 409
    assert first["bin_number"] == "SMCD1"


@pytest.mark.asyncio
async def test_list_bins_searches_bin_number(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()
    await client.post(
        "/api/bins",
        json={"label": "Glue Bin", "bin_number": "TCD1", "cabinet_id": cab["id"]},
        headers=headers,
    )

    r = await client.get("/api/bins?search=TCD1", headers=headers)
    assert r.status_code == 200
    assert [b["label"] for b in r.json()] == ["Glue Bin"]


@pytest.mark.asyncio
async def test_list_bins_by_cabinet(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)

    cab1 = (await client.post("/api/cabinets", json={"name": "C1", "room_id": room.id}, headers=headers)).json()
    cab2 = (await client.post("/api/cabinets", json={"name": "C2", "room_id": room.id}, headers=headers)).json()

    await client.post("/api/bins", json={"label": "A1", "bin_number": "C1A1", "cabinet_id": cab1["id"]}, headers=headers)
    await client.post("/api/bins", json={"label": "B1", "bin_number": "C1B1", "cabinet_id": cab1["id"]}, headers=headers)
    await client.post("/api/bins", json={"label": "X1", "bin_number": "C2X1", "cabinet_id": cab2["id"]}, headers=headers)

    r = await client.get(f"/api/bins?cabinet_id={cab1['id']}", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


# ─── Item tests ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_item(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)

    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    r = await client.post(
        "/api/items",
        json={"name": "Hammer", "quantity_total": 5, "cabinet_id": cab["id"], "sku": "SMC1"},
        headers=headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Hammer"
    assert data["sku"] == "SMC1"
    assert data["quantity_total"] == 5
    assert data["quantity_available"] == 5


@pytest.mark.asyncio
async def test_create_item_requires_sku(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    missing = await client.post(
        "/api/items",
        json={"name": "Hammer", "quantity_total": 5, "cabinet_id": cab["id"]},
        headers=headers,
    )
    assert missing.status_code == 422

    blank = await client.post(
        "/api/items",
        json={"name": "Hammer", "quantity_total": 5, "cabinet_id": cab["id"], "sku": "   "},
        headers=headers,
    )
    assert blank.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_item_sku_returns_conflict(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    first = await client.post(
        "/api/items",
        json={"name": "Hammer", "quantity_total": 1, "cabinet_id": cab["id"], "sku": "SMC1"},
        headers=headers,
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/items",
        json={"name": "Saw", "quantity_total": 1, "cabinet_id": cab["id"], "sku": "SMC1"},
        headers=headers,
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_duplicate_item_sku_case_insensitive_returns_conflict(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    first = await client.post(
        "/api/items",
        json={"name": "Hammer", "quantity_total": 1, "cabinet_id": cab["id"], "sku": "SMC1"},
        headers=headers,
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/items",
        json={"name": "Saw", "quantity_total": 1, "cabinet_id": cab["id"], "sku": "smc1"},
        headers=headers,
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_update_item_sku_case_insensitive_duplicate_returns_conflict(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    await client.post(
        "/api/items",
        json={"name": "Hammer", "quantity_total": 1, "cabinet_id": cab["id"], "sku": "SMC1"},
        headers=headers,
    )
    second = (await client.post(
        "/api/items",
        json={"name": "Saw", "quantity_total": 1, "cabinet_id": cab["id"], "sku": "SMC2"},
        headers=headers,
    )).json()

    r = await client.patch(f"/api/items/{second['id']}", json={"sku": "smc1"}, headers=headers)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_item_quantity_must_be_positive(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)

    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    r = await client.post(
        "/api/items",
        json={"name": "Hammer", "quantity_total": 0, "cabinet_id": cab["id"], "sku": "SMC1"},
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_update_item(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)

    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()
    item = (await client.post(
        "/api/items",
        json={"name": "Hammer", "quantity_total": 3, "cabinet_id": cab["id"], "sku": "SMC1"},
        headers=headers,
    )).json()

    r = await client.patch(f"/api/items/{item['id']}", json={"name": "Mallet"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Mallet"


@pytest.mark.asyncio
async def test_item_search_matches_name_sku_bin_label_and_bin_number(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()
    bin_ = (await client.post(
        "/api/bins",
        json={"label": "Glue Bin", "bin_number": "SMCD1", "cabinet_id": cab["id"]},
        headers=headers,
    )).json()
    item = (await client.post(
        "/api/items",
        json={
            "name": "Glue Gun",
            "quantity_total": 2,
            "cabinet_id": cab["id"],
            "bin_id": bin_["id"],
            "sku": "SMC17",
        },
        headers=headers,
    )).json()

    for term in ["Glue Gun", "SMC17", "Glue Bin", "SMCD1"]:
        r = await client.get("/api/items", params={"search": term}, headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert [i["id"] for i in data] == [item["id"]]
        assert data[0]["sku"] == "SMC17"
        assert data[0]["bin_number"] == "SMCD1"
        assert data[0]["bin_label"] == "Glue Bin"


@pytest.mark.asyncio
async def test_legacy_null_sku_item_and_null_bin_number_bin_are_readable(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = Cabinet(name="Cab", room_id=room.id)
    db.add(cab)
    await db.flush()
    legacy_bin = Bin(label="Legacy Bin", cabinet_id=cab.id, bin_number=None)
    db.add(legacy_bin)
    await db.flush()
    legacy_item = Item(
        name="Legacy Item",
        quantity_total=1,
        quantity_available=1,
        cabinet_id=cab.id,
        bin_id=legacy_bin.id,
        sku=None,
    )
    db.add(legacy_item)
    await db.commit()

    item_get = await client.get(f"/api/items/{legacy_item.id}", headers=headers)
    assert item_get.status_code == 200
    assert item_get.json()["sku"] is None
    assert item_get.json()["bin_number"] is None

    item_list = await client.get("/api/items", headers=headers)
    assert item_list.status_code == 200
    assert any(i["id"] == legacy_item.id and i["sku"] is None for i in item_list.json())

    bin_get = await client.get(f"/api/bins/{legacy_bin.id}", headers=headers)
    assert bin_get.status_code == 200
    assert bin_get.json()["bin_number"] is None

    bin_list = await client.get("/api/bins", headers=headers)
    assert bin_list.status_code == 200
    assert any(b["id"] == legacy_bin.id and b["bin_number"] is None for b in bin_list.json())


@pytest.mark.asyncio
async def test_db_blocks_case_insensitive_duplicate_item_sku(db: AsyncSession):
    room = await _make_room(db)
    cab = Cabinet(name="Cab", room_id=room.id)
    db.add(cab)
    await db.flush()
    db.add(Item(name="Hammer", quantity_total=1, quantity_available=1, cabinet_id=cab.id, sku="SMC1"))
    await db.commit()

    db.add(Item(name="Saw", quantity_total=1, quantity_available=1, cabinet_id=cab.id, sku="smc1"))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


@pytest.mark.asyncio
async def test_db_blocks_case_insensitive_duplicate_bin_number(db: AsyncSession):
    room = await _make_room(db)
    cab = Cabinet(name="Cab", room_id=room.id)
    db.add(cab)
    await db.flush()
    db.add(Bin(label="Glue Bin", cabinet_id=cab.id, bin_number="SMCD1"))
    await db.commit()

    db.add(Bin(label="Tape Bin", cabinet_id=cab.id, bin_number="smcd1"))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


@pytest.mark.asyncio
async def test_multiple_items_can_share_same_bin_number_through_same_bin(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()
    bin_ = (await client.post(
        "/api/bins",
        json={"label": "Glue Bin", "bin_number": "SMCD1", "cabinet_id": cab["id"]},
        headers=headers,
    )).json()

    first = await client.post(
        "/api/items",
        json={"name": "Glue Gun", "quantity_total": 1, "cabinet_id": cab["id"], "bin_id": bin_["id"], "sku": "SMC17"},
        headers=headers,
    )
    second = await client.post(
        "/api/items",
        json={"name": "Glue Sticks", "quantity_total": 5, "cabinet_id": cab["id"], "bin_id": bin_["id"], "sku": "SMC18"},
        headers=headers,
    )
    assert first.status_code == 201
    assert second.status_code == 201

    r = await client.get("/api/items", params={"search": "SMCD1"}, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert {i["sku"] for i in data} == {"SMC17", "SMC18"}
    assert {i["bin_number"] for i in data} == {"SMCD1"}


# ─── Bin requires_full_bin_checkout tests ─────────────────────────────────────

@pytest.mark.asyncio
async def test_create_bin_default_requires_full_checkout_false(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    r = await client.post(
        "/api/bins",
        json={"label": "B1", "bin_number": "TCB1", "cabinet_id": cab["id"]},
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["requires_full_bin_checkout"] is False


@pytest.mark.asyncio
async def test_create_bin_with_requires_full_checkout_true(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    r = await client.post(
        "/api/bins",
        json={"label": "B1", "bin_number": "TCB1", "cabinet_id": cab["id"], "requires_full_bin_checkout": True},
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["requires_full_bin_checkout"] is True


@pytest.mark.asyncio
async def test_update_bin_requires_full_checkout(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()
    bin_ = (await client.post(
        "/api/bins",
        json={"label": "B1", "bin_number": "TCB1", "cabinet_id": cab["id"]},
        headers=headers,
    )).json()
    assert bin_["requires_full_bin_checkout"] is False

    r = await client.patch(f"/api/bins/{bin_['id']}", json={"requires_full_bin_checkout": True}, headers=headers)
    assert r.status_code == 200
    assert r.json()["requires_full_bin_checkout"] is True


@pytest.mark.asyncio
async def test_bin_out_includes_requires_full_bin_checkout(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()
    await client.post(
        "/api/bins",
        json={"label": "B1", "bin_number": "TCB1", "cabinet_id": cab["id"], "requires_full_bin_checkout": True},
        headers=headers,
    )

    r = await client.get(f"/api/bins?cabinet_id={cab['id']}", headers=headers)
    assert r.status_code == 200
    bins = r.json()
    assert len(bins) == 1
    assert "requires_full_bin_checkout" in bins[0]
    assert bins[0]["requires_full_bin_checkout"] is True


@pytest.mark.asyncio
async def test_individual_checkout_blocked_when_bin_requires_full_checkout(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()
    bin_ = (await client.post(
        "/api/bins",
        json={"label": "B1", "bin_number": "TCB1", "cabinet_id": cab["id"], "requires_full_bin_checkout": True},
        headers=headers,
    )).json()
    item = (await client.post(
        "/api/items",
        json={"name": "Wrench", "quantity_total": 3, "cabinet_id": cab["id"], "bin_id": bin_["id"], "sku": "TCW1"},
        headers=headers,
    )).json()

    # Get admin user id from users list
    users = (await client.get("/api/users", headers=headers)).json()
    admin_id = next(u["id"] for u in users if u["username"] == "admin")
    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item["id"], "user_id": admin_id, "quantity": 1},
        headers=headers,
    )
    assert r.status_code == 409
    detail = r.json()["detail"].lower()
    assert "full" in detail or "whole" in detail


@pytest.mark.asyncio
async def test_individual_checkout_allowed_when_bin_does_not_require_full_checkout(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()
    bin_ = (await client.post(
        "/api/bins",
        json={"label": "B1", "bin_number": "TCB1", "cabinet_id": cab["id"], "requires_full_bin_checkout": False},
        headers=headers,
    )).json()
    item = (await client.post(
        "/api/items",
        json={"name": "Wrench", "quantity_total": 3, "cabinet_id": cab["id"], "bin_id": bin_["id"], "sku": "TCW1"},
        headers=headers,
    )).json()

    users = (await client.get("/api/users", headers=headers)).json()
    admin_id = next(u["id"] for u in users if u["username"] == "admin")
    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item["id"], "user_id": admin_id, "quantity": 1},
        headers=headers,
    )
    assert r.status_code == 201


# ─── Item requires_request schema unit tests ──────────────────────────────────

def test_item_create_schema_defaults_requires_request_to_false():
    from app.schemas.item import ItemCreate
    item = ItemCreate(name="Drill", quantity_total=1, cabinet_id=1, sku="TST1")
    assert item.requires_request is False


def test_item_create_schema_accepts_requires_request_true():
    from app.schemas.item import ItemCreate
    item = ItemCreate(name="Drill", quantity_total=1, cabinet_id=1, sku="TST1", requires_request=True)
    assert item.requires_request is True


def test_item_update_schema_accepts_requires_request():
    from app.schemas.item import ItemUpdate
    item = ItemUpdate(requires_request=False)
    assert item.requires_request is False
    item2 = ItemUpdate(requires_request=True)
    assert item2.requires_request is True


def test_item_update_schema_requires_request_defaults_to_none():
    from app.schemas.item import ItemUpdate
    item = ItemUpdate()
    assert item.requires_request is None


# ─── Item requires_request API tests ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_item_defaults_requires_request_to_false(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    r = await client.post(
        "/api/items",
        json={"name": "Hammer", "quantity_total": 1, "cabinet_id": cab["id"], "sku": "RRQ1"},
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["requires_request"] is False


@pytest.mark.asyncio
async def test_create_item_with_requires_request_true(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    r = await client.post(
        "/api/items",
        json={"name": "Drill Press", "quantity_total": 1, "cabinet_id": cab["id"], "sku": "RRQ2", "requires_request": True},
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["requires_request"] is True


@pytest.mark.asyncio
async def test_item_out_includes_requires_request(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    created = (await client.post(
        "/api/items",
        json={"name": "Saw", "quantity_total": 2, "cabinet_id": cab["id"], "sku": "RRQ3"},
        headers=headers,
    )).json()

    r = await client.get(f"/api/items/{created['id']}", headers=headers)
    assert r.status_code == 200
    assert "requires_request" in r.json()


@pytest.mark.asyncio
async def test_update_item_requires_request_false_to_true(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    item = (await client.post(
        "/api/items",
        json={"name": "Wrench", "quantity_total": 1, "cabinet_id": cab["id"], "sku": "RRQ4"},
        headers=headers,
    )).json()
    assert item["requires_request"] is False

    r = await client.patch(f"/api/items/{item['id']}", json={"requires_request": True}, headers=headers)
    assert r.status_code == 200
    assert r.json()["requires_request"] is True


@pytest.mark.asyncio
async def test_update_item_requires_request_true_to_false(client: AsyncClient, db: AsyncSession):
    await _seed_admin(db)
    token = await _login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {token}"}
    room = await _make_room(db)
    cab = (await client.post("/api/cabinets", json={"name": "Cab", "room_id": room.id}, headers=headers)).json()

    item = (await client.post(
        "/api/items",
        json={"name": "Lathe", "quantity_total": 1, "cabinet_id": cab["id"], "sku": "RRQ5", "requires_request": True},
        headers=headers,
    )).json()
    assert item["requires_request"] is True

    r = await client.patch(f"/api/items/{item['id']}", json={"requires_request": False}, headers=headers)
    assert r.status_code == 200
    assert r.json()["requires_request"] is False
