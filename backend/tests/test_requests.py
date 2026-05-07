"""
Inventory request lifecycle tests.

Covers: create, approve (service path == Telegram path), deny, list-by-status,
idempotency guards, API response serialization, group-lead scope enforcement
(web and Telegram), and notification-failure isolation.
"""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.core.exceptions import TransactionConflictError
from app.models.cabinet import Cabinet
from app.models.item import Item
from app.models.role import Role
from app.models.room import Room
from app.models.user import User
from app.services.request_service import approve_request, create_request, deny_request


# ─── Shared seed helpers ──────────────────────────────────────────────────────

async def _seed(db: AsyncSession):
    """Create minimal roles, users, and an item. Returns (approver, requester, item)."""
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
    db.add_all([coord_role, user_role])
    await db.flush()

    coordinator = User(
        full_name="Coord",
        username="coord",
        password_hash=hash_password("coordpass"),
        role_id=coord_role.id,
    )
    requester = User(
        full_name="Alice",
        username="alice",
        password_hash=hash_password("alicepass"),
        role_id=user_role.id,
    )
    db.add_all([coordinator, requester])

    room = Room(name="Test Room")
    db.add(room)
    await db.flush()

    cabinet = Cabinet(name="Cabinet A", room_id=room.id)
    db.add(cabinet)
    await db.flush()

    item = Item(
        name="Hammer",
        quantity_total=5,
        quantity_available=5,
        cabinet_id=cabinet.id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(coordinator)
    await db.refresh(requester)
    await db.refresh(item)
    return coordinator, requester, item


async def _login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ─── Service-level tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_request_status_is_pending(db: AsyncSession):
    coordinator, requester, item = await _seed(db)
    req = await create_request(
        db,
        requester_id=requester.id,
        item_id=item.id,
        bin_id=None,
        quantity_requested=2,
        reason="need it",
        due_at=None,
    )
    await db.commit()
    assert req.status == "PENDING"
    assert req.item_id == item.id


@pytest.mark.asyncio
async def test_approve_request_sets_fulfilled(db: AsyncSession):
    """Service-level approve (same code path used by Telegram /approve)."""
    coordinator, requester, item = await _seed(db)
    req = await create_request(
        db,
        requester_id=requester.id,
        item_id=item.id,
        bin_id=None,
        quantity_requested=2,
        reason=None,
        due_at=None,
    )
    await db.commit()

    fulfilled = await approve_request(
        db,
        request_id=req.id,
        approver_id=coordinator.id,
        due_at=None,
    )
    await db.commit()

    assert fulfilled.status == "FULFILLED"
    assert fulfilled.approver_id == coordinator.id
    assert fulfilled.fulfilled_at is not None


@pytest.mark.asyncio
async def test_approve_reduces_item_stock(db: AsyncSession):
    coordinator, requester, item = await _seed(db)
    req = await create_request(
        db,
        requester_id=requester.id,
        item_id=item.id,
        bin_id=None,
        quantity_requested=3,
        reason=None,
        due_at=None,
    )
    await db.commit()

    await approve_request(db, request_id=req.id, approver_id=coordinator.id, due_at=None)
    await db.commit()
    await db.refresh(item)

    assert item.quantity_available == 2  # 5 - 3


@pytest.mark.asyncio
async def test_double_approve_raises_conflict(db: AsyncSession):
    coordinator, requester, item = await _seed(db)
    req = await create_request(
        db,
        requester_id=requester.id,
        item_id=item.id,
        bin_id=None,
        quantity_requested=1,
        reason=None,
        due_at=None,
    )
    await db.commit()

    await approve_request(db, request_id=req.id, approver_id=coordinator.id, due_at=None)
    await db.commit()

    with pytest.raises(TransactionConflictError):
        await approve_request(db, request_id=req.id, approver_id=coordinator.id, due_at=None)


@pytest.mark.asyncio
async def test_deny_request_sets_denied(db: AsyncSession):
    coordinator, requester, item = await _seed(db)
    req = await create_request(
        db,
        requester_id=requester.id,
        item_id=item.id,
        bin_id=None,
        quantity_requested=1,
        reason=None,
        due_at=None,
    )
    await db.commit()

    denied = await deny_request(
        db,
        request_id=req.id,
        approver_id=coordinator.id,
        denial_reason="out of stock",
    )
    await db.commit()

    assert denied.status == "DENIED"
    assert denied.denial_reason == "out of stock"


@pytest.mark.asyncio
async def test_deny_already_processed_raises_conflict(db: AsyncSession):
    coordinator, requester, item = await _seed(db)
    req = await create_request(
        db,
        requester_id=requester.id,
        item_id=item.id,
        bin_id=None,
        quantity_requested=1,
        reason=None,
        due_at=None,
    )
    await db.commit()

    await deny_request(db, request_id=req.id, approver_id=coordinator.id, denial_reason=None)
    await db.commit()

    with pytest.raises(TransactionConflictError):
        await deny_request(db, request_id=req.id, approver_id=coordinator.id, denial_reason=None)


# ─── HTTP endpoint tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_http_create_and_list_request(client: AsyncClient, db: AsyncSession):
    coordinator, requester, item = await _seed(db)
    token = await _login(client, "alice", "alicepass")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/api/requests",
        json={"item_id": item.id, "quantity_requested": 1},
        headers=headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "PENDING"
    # quantity_requested must be a JSON number, not a string
    assert isinstance(data["quantity_requested"], (int, float)), (
        f"quantity_requested should be a number, got {type(data['quantity_requested'])!r}: "
        f"{data['quantity_requested']!r}"
    )

    list_r = await client.get("/api/requests?status=PENDING", headers=headers)
    assert list_r.status_code == 200
    assert len(list_r.json()) == 1


@pytest.mark.asyncio
async def test_http_approve_request(client: AsyncClient, db: AsyncSession):
    coordinator, requester, item = await _seed(db)
    alice_token = await _login(client, "alice", "alicepass")
    coord_token = await _login(client, "coord", "coordpass")

    create_r = await client.post(
        "/api/requests",
        json={"item_id": item.id, "quantity_requested": 2},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    req_id = create_r.json()["id"]

    approve_r = await client.post(
        f"/api/requests/{req_id}/approve",
        json={},
        headers={"Authorization": f"Bearer {coord_token}"},
    )
    assert approve_r.status_code == 200
    assert approve_r.json()["status"] == "FULFILLED"


@pytest.mark.asyncio
async def test_http_list_fulfilled_after_approval(client: AsyncClient, db: AsyncSession):
    coordinator, requester, item = await _seed(db)
    alice_token = await _login(client, "alice", "alicepass")
    coord_token = await _login(client, "coord", "coordpass")

    create_r = await client.post(
        "/api/requests",
        json={"item_id": item.id, "quantity_requested": 1},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    req_id = create_r.json()["id"]

    await client.post(
        f"/api/requests/{req_id}/approve",
        json={},
        headers={"Authorization": f"Bearer {coord_token}"},
    )

    # Fulfilled request must appear under FULFILLED filter
    list_r = await client.get(
        "/api/requests?status=FULFILLED",
        headers={"Authorization": f"Bearer {coord_token}"},
    )
    assert list_r.status_code == 200
    ids = [r["id"] for r in list_r.json()]
    assert req_id in ids

    # Must NOT appear under PENDING filter
    pending_r = await client.get(
        "/api/requests?status=PENDING",
        headers={"Authorization": f"Bearer {coord_token}"},
    )
    assert req_id not in [r["id"] for r in pending_r.json()]


@pytest.mark.asyncio
async def test_http_double_approve_returns_409(client: AsyncClient, db: AsyncSession):
    coordinator, requester, item = await _seed(db)
    alice_token = await _login(client, "alice", "alicepass")
    coord_token = await _login(client, "coord", "coordpass")

    create_r = await client.post(
        "/api/requests",
        json={"item_id": item.id, "quantity_requested": 1},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    req_id = create_r.json()["id"]

    headers = {"Authorization": f"Bearer {coord_token}"}
    await client.post(f"/api/requests/{req_id}/approve", json={}, headers=headers)
    second = await client.post(f"/api/requests/{req_id}/approve", json={}, headers=headers)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_http_deny_already_processed_returns_409(client: AsyncClient, db: AsyncSession):
    coordinator, requester, item = await _seed(db)
    alice_token = await _login(client, "alice", "alicepass")
    coord_token = await _login(client, "coord", "coordpass")

    create_r = await client.post(
        "/api/requests",
        json={"item_id": item.id, "quantity_requested": 1},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    req_id = create_r.json()["id"]

    headers = {"Authorization": f"Bearer {coord_token}"}
    await client.post(f"/api/requests/{req_id}/deny", json={"denial_reason": "no"}, headers=headers)
    second = await client.post(f"/api/requests/{req_id}/deny", json={}, headers=headers)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_quantity_requested_is_number_in_api(client: AsyncClient, db: AsyncSession):
    """Regression: quantity_requested must be a JSON number, not a string."""
    coordinator, requester, item = await _seed(db)
    alice_token = await _login(client, "alice", "alicepass")

    await client.post(
        "/api/requests",
        json={"item_id": item.id, "quantity_requested": 2},
        headers={"Authorization": f"Bearer {alice_token}"},
    )

    list_r = await client.get(
        "/api/requests",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert list_r.status_code == 200
    for req in list_r.json():
        qty = req["quantity_requested"]
        assert isinstance(qty, (int, float)), (
            f"quantity_requested must be int/float, got {type(qty)!r}: {qty!r}"
        )


# ─── Group-scope seed helper ──────────────────────────────────────────────────

async def _seed_two_groups(db: AsyncSession):
    """
    Create two group leads from different groups, two regular users, one admin,
    and one item with sufficient stock.
    Returns (gl1, gl2, user1, user2, admin, item).
    """
    gl_role = Role(
        name="GL_ROLE",
        can_manage_inventory=False,
        can_manage_cabinets=False,
        can_manage_bins=False,
        can_manage_users=False,
        can_process_any_transaction=True,
        can_view_all_transactions=True,
        can_view_audit_logs=False,
        can_approve_requests=True,
    )
    user_role = Role(
        name="USR_ROLE",
        can_manage_inventory=False,
        can_manage_cabinets=False,
        can_manage_bins=False,
        can_manage_users=False,
        can_process_any_transaction=False,
        can_view_all_transactions=False,
        can_view_audit_logs=False,
        can_approve_requests=False,
    )
    admin_role = Role(
        name="ADM_ROLE",
        can_manage_inventory=True,
        can_manage_cabinets=True,
        can_manage_bins=True,
        can_manage_users=True,
        can_process_any_transaction=True,
        can_view_all_transactions=True,
        can_view_audit_logs=True,
        can_approve_requests=True,
    )
    db.add_all([gl_role, user_role, admin_role])
    await db.flush()

    gl1 = User(full_name="GL One", username="gl1", password_hash=hash_password("gl1pass"),
               role_id=gl_role.id, group_name="GROUP_1")
    gl2 = User(full_name="GL Two", username="gl2", password_hash=hash_password("gl2pass"),
               role_id=gl_role.id, group_name="GROUP_2")
    user1 = User(full_name="User One", username="user1", password_hash=hash_password("u1pass"),
                 role_id=user_role.id, group_name="GROUP_1")
    user2 = User(full_name="User Two", username="user2", password_hash=hash_password("u2pass"),
                 role_id=user_role.id, group_name="GROUP_2")
    adm = User(full_name="Admin", username="adm", password_hash=hash_password("admpass"),
               role_id=admin_role.id, group_name=None)
    db.add_all([gl1, gl2, user1, user2, adm])

    room = Room(name="Room G")
    db.add(room)
    await db.flush()
    cabinet = Cabinet(name="Cabinet G", room_id=room.id)
    db.add(cabinet)
    await db.flush()
    item = Item(name="Wrench", quantity_total=10, quantity_available=10, cabinet_id=cabinet.id)
    db.add(item)
    await db.commit()

    for obj in (gl1, gl2, user1, user2, adm, item):
        await db.refresh(obj)

    return gl1, gl2, user1, user2, adm, item


# ─── Group-scope web endpoint tests ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_group_lead_can_approve_own_group(client: AsyncClient, db: AsyncSession):
    """Group lead may approve a request from a user in their own group."""
    gl1, gl2, user1, user2, adm, item = await _seed_two_groups(db)
    u1_token = await _login(client, "user1", "u1pass")
    gl1_token = await _login(client, "gl1", "gl1pass")

    create_r = await client.post(
        "/api/requests",
        json={"item_id": item.id, "quantity_requested": 1},
        headers={"Authorization": f"Bearer {u1_token}"},
    )
    assert create_r.status_code == 201
    req_id = create_r.json()["id"]

    approve_r = await client.post(
        f"/api/requests/{req_id}/approve",
        json={},
        headers={"Authorization": f"Bearer {gl1_token}"},
    )
    assert approve_r.status_code == 200
    assert approve_r.json()["status"] == "FULFILLED"


@pytest.mark.asyncio
async def test_group_lead_cannot_approve_other_group(client: AsyncClient, db: AsyncSession):
    """Group lead is forbidden from approving a request from another group."""
    gl1, gl2, user1, user2, adm, item = await _seed_two_groups(db)
    u2_token = await _login(client, "user2", "u2pass")
    gl1_token = await _login(client, "gl1", "gl1pass")

    create_r = await client.post(
        "/api/requests",
        json={"item_id": item.id, "quantity_requested": 1},
        headers={"Authorization": f"Bearer {u2_token}"},
    )
    req_id = create_r.json()["id"]

    approve_r = await client.post(
        f"/api/requests/{req_id}/approve",
        json={},
        headers={"Authorization": f"Bearer {gl1_token}"},
    )
    assert approve_r.status_code == 403


@pytest.mark.asyncio
async def test_group_lead_cannot_deny_other_group(client: AsyncClient, db: AsyncSession):
    """Group lead is forbidden from denying a request from another group."""
    gl1, gl2, user1, user2, adm, item = await _seed_two_groups(db)
    u2_token = await _login(client, "user2", "u2pass")
    gl1_token = await _login(client, "gl1", "gl1pass")

    create_r = await client.post(
        "/api/requests",
        json={"item_id": item.id, "quantity_requested": 1},
        headers={"Authorization": f"Bearer {u2_token}"},
    )
    req_id = create_r.json()["id"]

    deny_r = await client.post(
        f"/api/requests/{req_id}/deny",
        json={"denial_reason": "test"},
        headers={"Authorization": f"Bearer {gl1_token}"},
    )
    assert deny_r.status_code == 403


@pytest.mark.asyncio
async def test_scope_403_does_not_mutate_inventory(client: AsyncClient, db: AsyncSession):
    """A 403 scope rejection must leave the request PENDING and stock unchanged."""
    gl1, gl2, user1, user2, adm, item = await _seed_two_groups(db)
    u2_token = await _login(client, "user2", "u2pass")
    gl1_token = await _login(client, "gl1", "gl1pass")

    create_r = await client.post(
        "/api/requests",
        json={"item_id": item.id, "quantity_requested": 2},
        headers={"Authorization": f"Bearer {u2_token}"},
    )
    req_id = create_r.json()["id"]

    approve_r = await client.post(
        f"/api/requests/{req_id}/approve",
        json={},
        headers={"Authorization": f"Bearer {gl1_token}"},
    )
    assert approve_r.status_code == 403

    # Request must still be PENDING
    list_r = await client.get(
        "/api/requests?status=PENDING",
        headers={"Authorization": f"Bearer {gl1_token}"},
    )
    # gl1 can't see user2's requests (different group), but admin can
    adm_token = await _login(client, "adm", "admpass")
    detail_r = await client.get(
        f"/api/requests?status=PENDING",
        headers={"Authorization": f"Bearer {adm_token}"},
    )
    ids = [r["id"] for r in detail_r.json()]
    assert req_id in ids, "Request should still be PENDING after 403"

    # Stock must be unchanged
    await db.refresh(item)
    assert item.quantity_available == 10


@pytest.mark.asyncio
async def test_admin_can_approve_globally(client: AsyncClient, db: AsyncSession):
    """Admin (can_manage_users) may approve requests from any group."""
    gl1, gl2, user1, user2, adm, item = await _seed_two_groups(db)
    u2_token = await _login(client, "user2", "u2pass")
    adm_token = await _login(client, "adm", "admpass")

    create_r = await client.post(
        "/api/requests",
        json={"item_id": item.id, "quantity_requested": 1},
        headers={"Authorization": f"Bearer {u2_token}"},
    )
    req_id = create_r.json()["id"]

    approve_r = await client.post(
        f"/api/requests/{req_id}/approve",
        json={},
        headers={"Authorization": f"Bearer {adm_token}"},
    )
    assert approve_r.status_code == 200
    assert approve_r.json()["status"] == "FULFILLED"


@pytest.mark.asyncio
async def test_notification_failure_does_not_fail_approval(client: AsyncClient, db: AsyncSession):
    """
    A Telegram notification failure after a committed approval must not turn
    the HTTP response into an error (the approval already succeeded in the DB).
    """
    coordinator, requester, item = await _seed(db)
    # Give the requester a telegram_chat_id so the notification path is exercised.
    requester.telegram_chat_id = "alice_tg_123"
    await db.commit()

    alice_token = await _login(client, "alice", "alicepass")
    coord_token = await _login(client, "coord", "coordpass")

    create_r = await client.post(
        "/api/requests",
        json={"item_id": item.id, "quantity_requested": 1},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    req_id = create_r.json()["id"]

    with patch(
        "app.routers.inventory_requests.notify_request_approved",
        new=AsyncMock(side_effect=RuntimeError("Telegram API down")),
    ):
        approve_r = await client.post(
            f"/api/requests/{req_id}/approve",
            json={},
            headers={"Authorization": f"Bearer {coord_token}"},
        )

    # Approval must succeed despite notification failure.
    assert approve_r.status_code == 200, approve_r.text
    assert approve_r.json()["status"] == "FULFILLED"


@pytest.mark.asyncio
async def test_notification_failure_does_not_fail_denial(client: AsyncClient, db: AsyncSession):
    """Same isolation guarantee for the deny path."""
    coordinator, requester, item = await _seed(db)
    requester.telegram_chat_id = "alice_tg_456"
    await db.commit()

    alice_token = await _login(client, "alice", "alicepass")
    coord_token = await _login(client, "coord", "coordpass")

    create_r = await client.post(
        "/api/requests",
        json={"item_id": item.id, "quantity_requested": 1},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    req_id = create_r.json()["id"]

    with patch(
        "app.routers.inventory_requests.notify_request_denied",
        new=AsyncMock(side_effect=RuntimeError("Telegram API down")),
    ):
        deny_r = await client.post(
            f"/api/requests/{req_id}/deny",
            json={"denial_reason": "no stock"},
            headers={"Authorization": f"Bearer {coord_token}"},
        )

    assert deny_r.status_code == 200, deny_r.text
    assert deny_r.json()["status"] == "DENIED"


# ─── Telegram handler scope tests (direct handler invocation) ─────────────────

@pytest.mark.asyncio
async def test_telegram_approve_own_group(db: AsyncSession):
    """Telegram /approve succeeds when group lead acts on their own group's request."""
    gl1, gl2, user1, user2, adm, item = await _seed_two_groups(db)
    gl1.telegram_chat_id = "gl1_tg"
    await db.commit()
    await db.refresh(gl1)

    req = await create_request(
        db, requester_id=user1.id, item_id=item.id, bin_id=None,
        quantity_requested=1, reason=None, due_at=None,
    )
    await db.commit()
    await db.refresh(req)

    from app.bot.handlers import cmd_approve
    await cmd_approve("gl1_tg", "gl1_tg", str(req.id), db)

    await db.refresh(req)
    assert req.status == "FULFILLED"


@pytest.mark.asyncio
async def test_telegram_approve_cross_group_rejected(db: AsyncSession):
    """Telegram /approve is rejected when group lead targets another group's request."""
    gl1, gl2, user1, user2, adm, item = await _seed_two_groups(db)
    gl1.telegram_chat_id = "gl1_tg_x"
    await db.commit()
    await db.refresh(gl1)

    # user2 is in GROUP_2; gl1 is in GROUP_1
    req = await create_request(
        db, requester_id=user2.id, item_id=item.id, bin_id=None,
        quantity_requested=1, reason=None, due_at=None,
    )
    await db.commit()
    await db.refresh(req)

    from app.bot.handlers import cmd_approve
    await cmd_approve("gl1_tg_x", "gl1_tg_x", str(req.id), db)

    # Request must remain PENDING — no mutation.
    await db.refresh(req)
    assert req.status == "PENDING"


@pytest.mark.asyncio
async def test_telegram_deny_cross_group_rejected(db: AsyncSession):
    """Telegram /deny is rejected when group lead targets another group's request."""
    gl1, gl2, user1, user2, adm, item = await _seed_two_groups(db)
    gl1.telegram_chat_id = "gl1_tg_d"
    await db.commit()
    await db.refresh(gl1)

    req = await create_request(
        db, requester_id=user2.id, item_id=item.id, bin_id=None,
        quantity_requested=1, reason=None, due_at=None,
    )
    await db.commit()
    await db.refresh(req)

    from app.bot.handlers import cmd_deny
    await cmd_deny("gl1_tg_d", "gl1_tg_d", str(req.id), "nope", db)

    await db.refresh(req)
    assert req.status == "PENDING"


@pytest.mark.asyncio
async def test_telegram_requests_filters_by_group(db: AsyncSession):
    """Telegram /requests only shows requests from the group lead's own group."""
    gl1, gl2, user1, user2, adm, item = await _seed_two_groups(db)
    gl1.telegram_chat_id = "gl1_tg_list"
    await db.commit()
    await db.refresh(gl1)

    req1 = await create_request(
        db, requester_id=user1.id, item_id=item.id, bin_id=None,
        quantity_requested=1, reason=None, due_at=None,
    )
    req2 = await create_request(
        db, requester_id=user2.id, item_id=item.id, bin_id=None,
        quantity_requested=1, reason=None, due_at=None,
    )
    await db.commit()
    await db.refresh(req1)
    await db.refresh(req2)

    sent: list[str] = []

    async def capture_send(chat_id: str, text: str) -> None:
        sent.append(text)

    from app.bot import handlers as h
    with patch.object(h, "_send", side_effect=capture_send):
        await h.cmd_requests("gl1_tg_list", "gl1_tg_list", db)

    combined = "\n".join(sent)
    assert f"#{req1.id}" in combined, "gl1 should see user1's request (same group)"
    assert f"#{req2.id}" not in combined, "gl1 must not see user2's request (different group)"


# ─── Submission DM tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_request_dms_requester(client: AsyncClient, db: AsyncSession):
    """Submitting a request DMs the requester when their Telegram is linked."""
    coordinator, requester, item = await _seed(db)
    requester.telegram_chat_id = "alice_dm_tg"
    await db.commit()

    alice_token = await _login(client, "alice", "alicepass")

    with patch("app.services.telegram_service.notify_request_submitted", new=AsyncMock()) as mock_notify:
        r = await client.post(
            "/api/requests",
            json={"item_id": item.id, "quantity_requested": 1},
            headers={"Authorization": f"Bearer {alice_token}"},
        )

    assert r.status_code == 201
    mock_notify.assert_awaited_once()
    a = mock_notify.call_args.args
    assert a[0] == "alice_dm_tg"
    assert "Hammer" in a[1]


@pytest.mark.asyncio
async def test_submit_request_dm_failure_does_not_affect_response(client: AsyncClient, db: AsyncSession):
    """A failing submission DM must not affect the 201 response."""
    coordinator, requester, item = await _seed(db)
    requester.telegram_chat_id = "alice_dm_tg2"
    await db.commit()

    alice_token = await _login(client, "alice", "alicepass")

    with patch("app.services.telegram_service.notify_request_submitted",
               new=AsyncMock(side_effect=RuntimeError("Telegram down"))):
        r = await client.post(
            "/api/requests",
            json={"item_id": item.id, "quantity_requested": 1},
            headers={"Authorization": f"Bearer {alice_token}"},
        )

    assert r.status_code == 201
    assert r.json()["status"] == "PENDING"
