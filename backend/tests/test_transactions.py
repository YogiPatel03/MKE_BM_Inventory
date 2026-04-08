"""
Transaction tests: service-level and HTTP endpoint coverage.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.cabinet import Cabinet
from app.models.item import Item
from app.models.role import Role
from app.models.transaction import TransactionStatus
from app.models.user import User
from app.services.transaction_service import checkout_item, return_item


async def _seed(db: AsyncSession):
    role = Role(name="USER", can_manage_inventory=False, can_manage_cabinets=False,
                can_manage_bins=False, can_manage_users=False,
                can_process_any_transaction=False, can_view_all_transactions=False,
                can_view_audit_logs=False)
    db.add(role)
    await db.flush()

    user = User(full_name="Alice", username="alice",
                password_hash=hash_password("pass"), role_id=role.id)
    db.add(user)

    cabinet = Cabinet(name="Cabinet A")
    db.add(cabinet)
    await db.flush()

    item = Item(name="Hammer", quantity_total=3, quantity_available=3, cabinet_id=cabinet.id)
    db.add(item)
    await db.commit()
    await db.refresh(user)
    await db.refresh(item)
    return user, item


@pytest.mark.asyncio
async def test_checkout_decrements_availability(db: AsyncSession):
    user, item = await _seed(db)
    transaction = await checkout_item(
        db,
        item_id=item.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        quantity=2,
        due_at=None,
        notes=None,
    )
    await db.commit()
    await db.refresh(item)
    assert transaction.status == TransactionStatus.CHECKED_OUT
    assert item.quantity_available == 1


@pytest.mark.asyncio
async def test_insufficient_stock_raises(db: AsyncSession):
    from app.core.exceptions import InsufficientStockError
    user, item = await _seed(db)
    with pytest.raises(InsufficientStockError):
        await checkout_item(db, item_id=item.id, user_id=user.id,
                            processed_by_user_id=user.id, quantity=10,
                            due_at=None, notes=None)


@pytest.mark.asyncio
async def test_return_restores_availability(db: AsyncSession):
    user, item = await _seed(db)
    transaction = await checkout_item(db, item_id=item.id, user_id=user.id,
                                      processed_by_user_id=user.id, quantity=1,
                                      due_at=None, notes=None)
    await db.commit()

    returned = await return_item(db, transaction_id=transaction.id,
                                 processed_by_user_id=user.id, notes=None,
                                 requesting_user_id=user.id)
    await db.commit()
    await db.refresh(item)
    assert returned.status == TransactionStatus.RETURNED
    assert item.quantity_available == 3


# ─── HTTP endpoint tests ──────────────────────────────────────────────────────

async def _seed_with_admin(db: AsyncSession):
    admin_role = Role(
        name="ADMIN",
        can_manage_inventory=True, can_manage_cabinets=True, can_manage_bins=True,
        can_manage_users=True, can_process_any_transaction=True,
        can_view_all_transactions=True, can_view_audit_logs=True,
    )
    user_role = Role(
        name="USER",
        can_manage_inventory=False, can_manage_cabinets=False, can_manage_bins=False,
        can_manage_users=False, can_process_any_transaction=False,
        can_view_all_transactions=False, can_view_audit_logs=False,
    )
    db.add_all([admin_role, user_role])
    await db.flush()

    admin = User(full_name="Admin", username="admin", password_hash=hash_password("adminpass"), role_id=admin_role.id)
    alice = User(full_name="Alice", username="alice", password_hash=hash_password("alicepass"), role_id=user_role.id)
    db.add_all([admin, alice])

    cabinet = Cabinet(name="Cabinet A")
    db.add(cabinet)
    await db.flush()

    item = Item(name="Drill", quantity_total=3, quantity_available=3, cabinet_id=cabinet.id)
    db.add(item)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(alice)
    await db.refresh(item)
    return admin, alice, item


async def _login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_http_checkout_and_list(client: AsyncClient, db: AsyncSession):
    _, alice, item = await _seed_with_admin(db)
    token = await _login(client, "alice", "alicepass")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": alice.id, "quantity": 2},
        headers=headers,
    )
    assert r.status_code == 201
    tx = r.json()
    assert tx["status"] == "CHECKED_OUT"
    assert tx["quantity"] == 2

    list_r = await client.get("/api/transactions", headers=headers)
    assert list_r.status_code == 200
    assert len(list_r.json()) == 1


@pytest.mark.asyncio
async def test_http_return(client: AsyncClient, db: AsyncSession):
    _, alice, item = await _seed_with_admin(db)
    token = await _login(client, "alice", "alicepass")
    headers = {"Authorization": f"Bearer {token}"}

    checkout_r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
        headers=headers,
    )
    tx_id = checkout_r.json()["id"]

    return_r = await client.post(f"/api/transactions/{tx_id}/return", json={}, headers=headers)
    assert return_r.status_code == 200
    assert return_r.json()["status"] == "RETURNED"


@pytest.mark.asyncio
async def test_http_cancel_by_admin(client: AsyncClient, db: AsyncSession):
    _, alice, item = await _seed_with_admin(db)
    alice_token = await _login(client, "alice", "alicepass")
    admin_token = await _login(client, "admin", "adminpass")

    checkout_r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    tx_id = checkout_r.json()["id"]

    cancel_r = await client.post(
        f"/api/transactions/{tx_id}/cancel",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert cancel_r.status_code == 200
    assert cancel_r.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_http_double_return_fails(client: AsyncClient, db: AsyncSession):
    _, alice, item = await _seed_with_admin(db)
    token = await _login(client, "alice", "alicepass")
    headers = {"Authorization": f"Bearer {token}"}

    checkout_r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
        headers=headers,
    )
    tx_id = checkout_r.json()["id"]

    await client.post(f"/api/transactions/{tx_id}/return", json={}, headers=headers)
    second_return = await client.post(f"/api/transactions/{tx_id}/return", json={}, headers=headers)
    assert second_return.status_code == 409


@pytest.mark.asyncio
async def test_http_checkout_exceeds_stock(client: AsyncClient, db: AsyncSession):
    _, alice, item = await _seed_with_admin(db)
    token = await _login(client, "alice", "alicepass")

    r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": alice.id, "quantity": 999},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_http_get_transaction_detail(client: AsyncClient, db: AsyncSession):
    _, alice, item = await _seed_with_admin(db)
    admin_token = await _login(client, "admin", "adminpass")

    checkout_r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    tx_id = checkout_r.json()["id"]

    detail_r = await client.get(
        f"/api/transactions/{tx_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert detail_r.status_code == 200
    data = detail_r.json()
    assert data["id"] == tx_id
    assert "item" in data
    assert "user" in data
