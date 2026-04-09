"""
Tests for:
- ActivityLog creation
- Usage event reversal
- Low-stock threshold logic
- Restock Me auto-move
- Admin password reset
- Edit-after-creation (item, cabinet)
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import hash_password
from app.models.cabinet import Cabinet
from app.models.role import Role
from app.models.user import User
from app.models.activity_log import ActivityLog, ActivityType
from app.models.item import Item


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _seed_admin(db: AsyncSession):
    role = Role(
        name="ADMIN2",
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
        username="admin2",
        password_hash=hash_password("adminpass2"),
        role_id=role.id,
    )
    db.add(user)
    await db.commit()
    return user, role


async def _login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _setup_cabinet_and_consumable(client, headers) -> tuple[dict, dict]:
    """Returns (cabinet, consumable_item) as JSON dicts."""
    cab = (await client.post("/api/cabinets", json={"name": "Test Cabinet X"}, headers=headers)).json()
    item = (await client.post(
        "/api/items",
        json={
            "name": "Batteries",
            "quantity_total": 20,
            "cabinet_id": cab["id"],
            "is_consumable": True,
            "unit_price": 2.50,
        },
        headers=headers,
    )).json()
    return cab, item


# ─── Activity Log ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_item_create_logs_activity(client: AsyncClient, db: AsyncSession):
    _, _ = await _seed_admin(db)
    token = await _login(client, "admin2", "adminpass2")
    headers = {"Authorization": f"Bearer {token}"}

    cab = (await client.post("/api/cabinets", json={"name": "Cab-Activity"}, headers=headers)).json()
    item = (await client.post(
        "/api/items",
        json={"name": "Widget", "quantity_total": 5, "cabinet_id": cab["id"]},
        headers=headers,
    )).json()

    # Check activity log via API
    r = await client.get("/api/activity", params={"activity_type": "ITEM_CREATED"}, headers=headers)
    assert r.status_code == 200
    activities = r.json()
    assert len(activities) >= 1
    created = next((a for a in activities if a["target_item_id"] == item["id"]), None)
    assert created is not None
    assert created["activity_type"] == "ITEM_CREATED"
    assert created["quantity_delta"] == 5


@pytest.mark.asyncio
async def test_usage_logs_activity(client: AsyncClient, db: AsyncSession):
    _, _ = await _seed_admin(db)
    token = await _login(client, "admin2", "adminpass2")
    headers = {"Authorization": f"Bearer {token}"}

    _, item = await _setup_cabinet_and_consumable(client, headers)

    r = await client.post("/api/usage-events", json={"item_id": item["id"], "quantity_used": 3}, headers=headers)
    assert r.status_code == 201

    activity_r = await client.get("/api/activity", params={"activity_type": "USAGE_RECORDED"}, headers=headers)
    assert activity_r.status_code == 200
    activities = activity_r.json()
    usage_act = next((a for a in activities if a["target_item_id"] == item["id"]), None)
    assert usage_act is not None
    assert usage_act["quantity_delta"] == -3


@pytest.mark.asyncio
async def test_item_edit_logs_activity(client: AsyncClient, db: AsyncSession):
    _, _ = await _seed_admin(db)
    token = await _login(client, "admin2", "adminpass2")
    headers = {"Authorization": f"Bearer {token}"}

    _, item = await _setup_cabinet_and_consumable(client, headers)

    patch_r = await client.patch(f"/api/items/{item['id']}", json={"name": "Batteries v2"}, headers=headers)
    assert patch_r.status_code == 200

    activity_r = await client.get("/api/activity", params={"activity_type": "ITEM_EDITED"}, headers=headers)
    activities = activity_r.json()
    edit_act = next((a for a in activities if a["target_item_id"] == item["id"]), None)
    assert edit_act is not None
    assert edit_act["activity_type"] == "ITEM_EDITED"


@pytest.mark.asyncio
async def test_cabinet_edit_logs_activity(client: AsyncClient, db: AsyncSession):
    _, _ = await _seed_admin(db)
    token = await _login(client, "admin2", "adminpass2")
    headers = {"Authorization": f"Bearer {token}"}

    cab = (await client.post("/api/cabinets", json={"name": "Cab-Edit-Test"}, headers=headers)).json()
    patch_r = await client.patch(f"/api/cabinets/{cab['id']}", json={"name": "Updated Cabinet"}, headers=headers)
    assert patch_r.status_code == 200

    activity_r = await client.get("/api/activity", params={"activity_type": "CABINET_EDITED"}, headers=headers)
    activities = activity_r.json()
    edit_act = next((a for a in activities if a["target_cabinet_id"] == cab["id"]), None)
    assert edit_act is not None


# ─── Usage Reversal ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_usage_reversal_restores_quantity(client: AsyncClient, db: AsyncSession):
    _, _ = await _seed_admin(db)
    token = await _login(client, "admin2", "adminpass2")
    headers = {"Authorization": f"Bearer {token}"}

    _, item = await _setup_cabinet_and_consumable(client, headers)
    item_id = item["id"]

    # Use 5 units
    r = await client.post("/api/usage-events", json={"item_id": item_id, "quantity_used": 5}, headers=headers)
    assert r.status_code == 201
    event_id = r.json()["id"]

    # Check quantity dropped
    item_r = await client.get(f"/api/items/{item_id}", headers=headers)
    assert item_r.json()["quantity_available"] == 15  # 20 - 5

    # Reverse the event
    rev_r = await client.post(f"/api/usage-events/{event_id}/reverse", json={}, headers=headers)
    assert rev_r.status_code == 201
    assert rev_r.json()["is_reversal"] is True
    assert rev_r.json()["reverses_event_id"] == event_id

    # Quantity should be restored
    item_r2 = await client.get(f"/api/items/{item_id}", headers=headers)
    assert item_r2.json()["quantity_available"] == 20

    # Activity log should show reversal
    activity_r = await client.get("/api/activity", params={"activity_type": "USAGE_REVERSED"}, headers=headers)
    activities = activity_r.json()
    rev_act = next((a for a in activities if a["target_item_id"] == item_id), None)
    assert rev_act is not None
    assert rev_act["quantity_delta"] == 5  # positive (restored)


@pytest.mark.asyncio
async def test_usage_reversal_blocks_double_reversal(client: AsyncClient, db: AsyncSession):
    _, _ = await _seed_admin(db)
    token = await _login(client, "admin2", "adminpass2")
    headers = {"Authorization": f"Bearer {token}"}

    _, item = await _setup_cabinet_and_consumable(client, headers)

    r = await client.post("/api/usage-events", json={"item_id": item["id"], "quantity_used": 2}, headers=headers)
    event_id = r.json()["id"]

    await client.post(f"/api/usage-events/{event_id}/reverse", json={}, headers=headers)

    # Second reversal should fail
    r2 = await client.post(f"/api/usage-events/{event_id}/reverse", json={}, headers=headers)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_usage_expense_report_nets_reversals(client: AsyncClient, db: AsyncSession):
    """Reversed usage events should not appear in expense totals."""
    _, _ = await _seed_admin(db)
    token = await _login(client, "admin2", "adminpass2")
    headers = {"Authorization": f"Bearer {token}"}

    _, item = await _setup_cabinet_and_consumable(client, headers)

    # Log a purchase first so unit_price is known
    await client.post("/api/purchases", json={
        "item_id": item["id"],
        "quantity_purchased": 0,  # just to set price
        "unit_price": 2.50,
        "total_price": 0,
    }, headers=headers)

    # Use 4, then reverse
    r = await client.post("/api/usage-events", json={"item_id": item["id"], "quantity_used": 4}, headers=headers)
    event_id = r.json()["id"]
    await client.post(f"/api/usage-events/{event_id}/reverse", json={}, headers=headers)

    # Expense report should show 0 usage cost for this item
    expense_r = await client.get(
        "/api/reports/expenses",
        params={"item_id": item["id"]},
        headers=headers,
    )
    data = expense_r.json()
    # Either by_usage is empty or total_usage_cost is 0
    assert data["total_usage_cost"] == 0.0 or all(
        u["total_cost"] == 0 for u in data["by_usage"]
    )


# ─── Low-Stock Threshold ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_low_stock_threshold_default_ten_percent(client: AsyncClient, db: AsyncSession):
    """Items with no explicit threshold: low stock when ≤ 10% remaining."""
    _, _ = await _seed_admin(db)
    token = await _login(client, "admin2", "adminpass2")
    headers = {"Authorization": f"Bearer {token}"}

    cab = (await client.post("/api/cabinets", json={"name": "Cab-Thresh"}, headers=headers)).json()
    # 100 total, no explicit threshold → dynamic threshold = max(1, 100 // 10) = 10
    item = (await client.post(
        "/api/items",
        json={"name": "Widgets", "quantity_total": 100, "cabinet_id": cab["id"]},
        headers=headers,
    )).json()

    # Not low stock yet
    status_r = await client.get("/api/reports/inventory-status", headers=headers)
    status = status_r.json()
    low_ids = [i["item_id"] for i in status["low_stock_items"]]
    assert item["id"] not in low_ids

    # Adjust down to 1 unit (delta=-99). Stock adjustments change both total and available.
    # After: quantity_total=1, quantity_available=1, threshold=max(1, 1//10)=1
    # 1 <= 1 → low stock ✓
    await client.post("/api/stock-adjustments", json={
        "item_id": item["id"], "delta": -99, "reason": "CORRECTION"
    }, headers=headers)

    status_r2 = await client.get("/api/reports/inventory-status", headers=headers)
    status2 = status_r2.json()
    low_ids2 = [i["item_id"] for i in status2["low_stock_items"]]
    assert item["id"] in low_ids2


@pytest.mark.asyncio
async def test_low_stock_threshold_explicit(client: AsyncClient, db: AsyncSession):
    """Explicit low_stock_threshold overrides the 10% default."""
    _, _ = await _seed_admin(db)
    token = await _login(client, "admin2", "adminpass2")
    headers = {"Authorization": f"Bearer {token}"}

    cab = (await client.post("/api/cabinets", json={"name": "Cab-Explicit"}, headers=headers)).json()
    item = (await client.post(
        "/api/items",
        json={"name": "Bolts", "quantity_total": 100, "cabinet_id": cab["id"], "low_stock_threshold": 25},
        headers=headers,
    )).json()

    # Adjust to 20 — below explicit threshold of 25
    await client.post("/api/stock-adjustments", json={
        "item_id": item["id"], "delta": -80, "reason": "CORRECTION"
    }, headers=headers)

    status_r = await client.get("/api/reports/inventory-status", headers=headers)
    status = status_r.json()
    low_ids = [i["item_id"] for i in status["low_stock_items"]]
    assert item["id"] in low_ids


@pytest.mark.asyncio
async def test_out_of_stock_item_appears_in_report(client: AsyncClient, db: AsyncSession):
    _, _ = await _seed_admin(db)
    token = await _login(client, "admin2", "adminpass2")
    headers = {"Authorization": f"Bearer {token}"}

    cab = (await client.post("/api/cabinets", json={"name": "Cab-OOS"}, headers=headers)).json()
    item = (await client.post(
        "/api/items",
        json={"name": "Tape", "quantity_total": 5, "cabinet_id": cab["id"], "is_consumable": True},
        headers=headers,
    )).json()

    # Use all stock
    await client.post("/api/usage-events", json={"item_id": item["id"], "quantity_used": 5}, headers=headers)

    status_r = await client.get("/api/reports/inventory-status", headers=headers)
    status = status_r.json()
    oos_ids = [i["item_id"] for i in status["out_of_stock_items"]]
    assert item["id"] in oos_ids
    # Should NOT appear in low stock (it's zero, not just low)
    low_ids = [i["item_id"] for i in status["low_stock_items"]]
    assert item["id"] not in low_ids


# ─── Restock Me Auto-Move ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_restock_me_auto_move_on_zero(client: AsyncClient, db: AsyncSession):
    """When a consumable hits zero, it should move to 'Restock Me' cabinet."""
    _, _ = await _seed_admin(db)
    token = await _login(client, "admin2", "adminpass2")
    headers = {"Authorization": f"Bearer {token}"}

    cab = (await client.post("/api/cabinets", json={"name": "Main Cabinet"}, headers=headers)).json()
    item = (await client.post(
        "/api/items",
        json={"name": "Gloves", "quantity_total": 2, "cabinet_id": cab["id"], "is_consumable": True},
        headers=headers,
    )).json()
    item_id = item["id"]
    original_cabinet_id = cab["id"]

    # Use all stock
    r = await client.post("/api/usage-events", json={"item_id": item_id, "quantity_used": 2}, headers=headers)
    assert r.status_code == 201

    # Item should now be in Restock Me cabinet
    item_r = await client.get(f"/api/items/{item_id}", headers=headers)
    item_data = item_r.json()
    assert item_data["quantity_available"] == 0
    assert item_data["prior_cabinet_id"] == original_cabinet_id

    # The new cabinet should be "Restock Me"
    cabs_r = await client.get("/api/cabinets", headers=headers)
    cabs = cabs_r.json()
    restock_cab = next((c for c in cabs if c["name"] == "Restock Me"), None)
    assert restock_cab is not None
    assert item_data["cabinet_id"] == restock_cab["id"]

    # Activity log should show auto-move
    activity_r = await client.get("/api/activity", params={"activity_type": "ITEM_MOVED_TO_RESTOCK"}, headers=headers)
    activities = activity_r.json()
    move_act = next((a for a in activities if a["target_item_id"] == item_id), None)
    assert move_act is not None


@pytest.mark.asyncio
async def test_restock_me_auto_restore_on_restock(client: AsyncClient, db: AsyncSession):
    """When usage is reversed (stock restored), item should return from Restock Me."""
    _, _ = await _seed_admin(db)
    token = await _login(client, "admin2", "adminpass2")
    headers = {"Authorization": f"Bearer {token}"}

    cab = (await client.post("/api/cabinets", json={"name": "Original Cabinet"}, headers=headers)).json()
    item = (await client.post(
        "/api/items",
        json={"name": "Clips", "quantity_total": 3, "cabinet_id": cab["id"], "is_consumable": True},
        headers=headers,
    )).json()
    item_id = item["id"]

    # Use all stock → moves to Restock Me
    r = await client.post("/api/usage-events", json={"item_id": item_id, "quantity_used": 3}, headers=headers)
    event_id = r.json()["id"]

    # Reverse → should restore to original cabinet
    await client.post(f"/api/usage-events/{event_id}/reverse", json={}, headers=headers)

    item_r = await client.get(f"/api/items/{item_id}", headers=headers)
    item_data = item_r.json()
    assert item_data["quantity_available"] == 3
    assert item_data["cabinet_id"] == cab["id"]
    assert item_data["prior_cabinet_id"] is None  # cleared after restore

    # Activity should show restoration
    activity_r = await client.get("/api/activity", params={"activity_type": "ITEM_RESTORED_FROM_RESTOCK"}, headers=headers)
    activities = activity_r.json()
    restore_act = next((a for a in activities if a["target_item_id"] == item_id), None)
    assert restore_act is not None


# ─── Admin Password Reset ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_password_reset(client: AsyncClient, db: AsyncSession):
    _, _ = await _seed_admin(db)
    token = await _login(client, "admin2", "adminpass2")
    headers = {"Authorization": f"Bearer {token}"}

    # Create another user
    user_role = Role(
        name="USER_PR",
        can_manage_inventory=False,
        can_manage_cabinets=False,
        can_manage_bins=False,
        can_manage_users=False,
        can_process_any_transaction=False,
        can_view_all_transactions=False,
        can_view_audit_logs=False,
        can_approve_requests=False,
    )
    db.add(user_role)
    await db.flush()
    target = User(
        full_name="Test Target",
        username="target_user",
        password_hash=hash_password("oldpassword"),
        role_id=user_role.id,
    )
    db.add(target)
    await db.commit()

    # Reset via admin
    r = await client.post(
        f"/api/users/{target.id}/reset-password",
        json={"new_password": "newpassword123"},
        headers=headers,
    )
    assert r.status_code == 204

    # New password should work
    login_r = await client.post("/api/auth/login", json={"username": "target_user", "password": "newpassword123"})
    assert login_r.status_code == 200

    # Old password should not
    login_r2 = await client.post("/api/auth/login", json={"username": "target_user", "password": "oldpassword"})
    assert login_r2.status_code == 401

    # Activity log should show reset
    activity_r = await client.get("/api/activity", params={"activity_type": "USER_PASSWORD_RESET"}, headers=headers)
    activities = activity_r.json()
    reset_act = next((a for a in activities if a["target_user_id"] == target.id), None)
    assert reset_act is not None


@pytest.mark.asyncio
async def test_password_reset_requires_min_length(client: AsyncClient, db: AsyncSession):
    _, _ = await _seed_admin(db)
    token = await _login(client, "admin2", "adminpass2")
    headers = {"Authorization": f"Bearer {token}"}

    user_role = Role(name="USER_PR2", can_manage_inventory=False, can_manage_cabinets=False,
                     can_manage_bins=False, can_manage_users=False, can_process_any_transaction=False,
                     can_view_all_transactions=False, can_view_audit_logs=False, can_approve_requests=False)
    db.add(user_role)
    await db.flush()
    target = User(full_name="T2", username="target2", password_hash=hash_password("old"), role_id=user_role.id)
    db.add(target)
    await db.commit()

    r = await client.post(
        f"/api/users/{target.id}/reset-password",
        json={"new_password": "short"},
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_admin_can_update_username(client: AsyncClient, db: AsyncSession):
    _, _ = await _seed_admin(db)
    token = await _login(client, "admin2", "adminpass2")
    headers = {"Authorization": f"Bearer {token}"}

    user_role = Role(name="USER_UN", can_manage_inventory=False, can_manage_cabinets=False,
                     can_manage_bins=False, can_manage_users=False, can_process_any_transaction=False,
                     can_view_all_transactions=False, can_view_audit_logs=False, can_approve_requests=False)
    db.add(user_role)
    await db.flush()
    target = User(full_name="Original", username="original_user", password_hash=hash_password("pass1234"), role_id=user_role.id)
    db.add(target)
    await db.commit()

    r = await client.patch(f"/api/users/{target.id}", json={"username": "updated_user"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["username"] == "updated_user"
