import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.role import Role
from app.models.user import User


async def _seed_user(db: AsyncSession) -> User:
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
    await db.flush()

    user = User(
        full_name="Test User",
        username="testuser",
        password_hash=hash_password("password123"),
        role_id=role.id,
    )
    db.add(user)
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, db: AsyncSession):
    await _seed_user(db)
    response = await client.post("/api/auth/login", json={"username": "testuser", "password": "password123"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, db: AsyncSession):
    await _seed_user(db)
    response = await client.post("/api/auth/login", json={"username": "testuser", "password": "wrong"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient, db: AsyncSession):
    response = await client.post("/api/auth/login", json={"username": "nobody", "password": "pass"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient):
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user(client: AsyncClient, db: AsyncSession):
    await _seed_user(db)
    login = await client.post("/api/auth/login", json={"username": "testuser", "password": "password123"})
    token = login.json()["access_token"]

    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "testuser"
