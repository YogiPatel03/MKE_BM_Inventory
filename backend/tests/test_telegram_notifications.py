"""
Telegram personal DM notification tests.

Covers:
- Item checkout DM to borrower + coordinator notification
- Item return DM to borrower
- Bin checkout DM to borrower + coordinator notification
- Bin return DM to borrower + coordinator notification
- DM failures do not rollback DB changes
- Unlinked users are skipped safely
- Low-stock/out-of-stock remain coordinator-only
- Overdue reminder loop continues after one user DM fails
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, call, patch

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.bin import Bin
from app.models.bin_transaction import BinTransaction
from app.models.cabinet import Cabinet
from app.models.item import Item
from app.models.role import Role
from app.models.room import Room
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User


# ─── Helpers ──────────────────────────────────────────────────────────────────

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


async def _seed(db: AsyncSession):
    """Seed admin + alice + item + bin for notification tests."""
    admin_role = _role(
        "NOTIF_ADMIN",
        can_manage_inventory=True,
        can_manage_cabinets=True,
        can_manage_bins=True,
        can_manage_users=True,
        can_process_any_transaction=True,
        can_view_all_transactions=True,
        can_view_audit_logs=True,
        can_approve_requests=True,
    )
    user_role = _role("NOTIF_USER")
    db.add_all([admin_role, user_role])
    await db.flush()

    admin = User(
        full_name="Admin",
        username="notif_admin",
        password_hash=hash_password("adminpass"),
        role_id=admin_role.id,
    )
    alice = User(
        full_name="Alice",
        username="notif_alice",
        password_hash=hash_password("alicepass"),
        role_id=user_role.id,
    )
    db.add_all([admin, alice])

    room = Room(name="Notif Test Room")
    db.add(room)
    await db.flush()

    cabinet = Cabinet(name="Notif Cabinet", room_id=room.id)
    db.add(cabinet)
    await db.flush()

    item = Item(
        name="Drill",
        quantity_total=Decimal("5"),
        quantity_available=Decimal("5"),
        cabinet_id=cabinet.id,
    )
    bin_obj = Bin(label="Alpha Bin", cabinet_id=cabinet.id)
    db.add_all([item, bin_obj])
    await db.commit()

    for obj in [admin, alice, item, bin_obj]:
        await db.refresh(obj)

    return admin, alice, item, bin_obj


async def _login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ─── Item checkout DM ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkout_item_sends_borrower_dm(client: AsyncClient, db: AsyncSession):
    """Item checkout sends DM to borrower when Telegram is linked."""
    _, alice, item, _ = await _seed(db)
    alice.telegram_chat_id = "alice_checkout_dm"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    with patch("app.services.telegram_service._send", new=AsyncMock(return_value=1)) as mock_send:
        r = await client.post(
            "/api/transactions/checkout",
            json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 201
    dm_calls = [c for c in mock_send.call_args_list if c.args[0] == "alice_checkout_dm"]
    assert dm_calls, "Expected a DM to the borrower's chat_id"
    dm_text = dm_calls[0].args[1]
    assert "Drill" in dm_text
    assert "Checkout confirmed" in dm_text


@pytest.mark.asyncio
async def test_checkout_item_succeeds_if_dm_fails(client: AsyncClient, db: AsyncSession):
    """Checkout succeeds even when the Telegram DM fails (returns None)."""
    _, alice, item, _ = await _seed(db)
    alice.telegram_chat_id = "alice_checkout_fail"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    with patch("app.services.telegram_service._send", new=AsyncMock(return_value=None)):
        r = await client.post(
            "/api/transactions/checkout",
            json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 201
    assert r.json()["status"] == "CHECKED_OUT"

    result = await db.execute(select(Transaction).where(Transaction.user_id == alice.id))
    txn = result.scalar_one_or_none()
    assert txn is not None
    assert txn.status == TransactionStatus.CHECKED_OUT


# ─── Item return DM ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_return_item_sends_borrower_dm(client: AsyncClient, db: AsyncSession):
    """Item return sends DM to borrower when Telegram is linked."""
    _, alice, item, _ = await _seed(db)
    alice.telegram_chat_id = "alice_return_dm"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    checkout_r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    tx_id = checkout_r.json()["id"]

    with patch("app.services.telegram_service._send", new=AsyncMock(return_value=1)) as mock_send:
        r = await client.post(
            f"/api/transactions/{tx_id}/return",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200
    dm_calls = [c for c in mock_send.call_args_list if c.args[0] == "alice_return_dm"]
    assert dm_calls, "Expected a DM to the borrower's chat_id"
    dm_text = dm_calls[0].args[1]
    assert "Return logged" in dm_text
    assert "Drill" in dm_text


@pytest.mark.asyncio
async def test_return_item_succeeds_if_dm_fails(client: AsyncClient, db: AsyncSession):
    """Return succeeds even when the Telegram DM fails (returns None)."""
    _, alice, item, _ = await _seed(db)
    alice.telegram_chat_id = "alice_return_fail"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    checkout_r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    tx_id = checkout_r.json()["id"]

    with patch("app.services.telegram_service._send", new=AsyncMock(return_value=None)):
        r = await client.post(
            f"/api/transactions/{tx_id}/return",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200
    assert r.json()["status"] == "RETURNED"

    result = await db.execute(select(Transaction).where(Transaction.id == tx_id))
    txn = result.scalar_one()
    assert txn.status == TransactionStatus.RETURNED


# ─── Bin checkout DM ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkout_bin_sends_borrower_dm(client: AsyncClient, db: AsyncSession):
    """Bin checkout sends DM to borrower and coordinator notification."""
    _, alice, _, bin_obj = await _seed(db)
    alice.telegram_chat_id = "alice_bin_checkout_dm"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    with patch("app.services.telegram_service._send", new=AsyncMock(return_value=1)) as mock_send:
        r = await client.post(
            "/api/bin-transactions",
            json={"bin_id": bin_obj.id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 201
    dm_calls = [c for c in mock_send.call_args_list if c.args[0] == "alice_bin_checkout_dm"]
    assert dm_calls, "Expected a DM to the borrower's chat_id"
    dm_text = dm_calls[0].args[1]
    assert "Alpha Bin" in dm_text
    assert "Bin checkout confirmed" in dm_text


@pytest.mark.asyncio
async def test_checkout_bin_succeeds_if_dm_fails(client: AsyncClient, db: AsyncSession):
    """Bin checkout succeeds even when Telegram DM fails (returns None)."""
    _, alice, _, bin_obj = await _seed(db)
    alice.telegram_chat_id = "alice_bin_checkout_fail"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    with patch("app.services.telegram_service._send", new=AsyncMock(return_value=None)):
        r = await client.post(
            "/api/bin-transactions",
            json={"bin_id": bin_obj.id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 201

    result = await db.execute(select(BinTransaction).where(BinTransaction.user_id == alice.id))
    bin_txn = result.scalar_one_or_none()
    assert bin_txn is not None
    assert bin_txn.status == "CHECKED_OUT"


# ─── Bin return DM ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_return_bin_sends_borrower_dm(client: AsyncClient, db: AsyncSession):
    """Bin return sends DM to borrower and coordinator notification."""
    _, alice, _, bin_obj = await _seed(db)
    alice.telegram_chat_id = "alice_bin_return_dm"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    checkout_r = await client.post(
        "/api/bin-transactions",
        json={"bin_id": bin_obj.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    bin_txn_id = checkout_r.json()["id"]

    with patch("app.services.telegram_service._send", new=AsyncMock(return_value=1)) as mock_send:
        r = await client.post(
            f"/api/bin-transactions/{bin_txn_id}/return",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200
    dm_calls = [c for c in mock_send.call_args_list if c.args[0] == "alice_bin_return_dm"]
    assert dm_calls, "Expected a DM to the borrower's chat_id"
    dm_text = dm_calls[0].args[1]
    assert "Bin return recorded" in dm_text
    assert "Alpha Bin" in dm_text


@pytest.mark.asyncio
async def test_return_bin_succeeds_if_dm_fails(client: AsyncClient, db: AsyncSession):
    """Bin return succeeds even when Telegram DM fails (returns None)."""
    _, alice, _, bin_obj = await _seed(db)
    alice.telegram_chat_id = "alice_bin_return_fail"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    checkout_r = await client.post(
        "/api/bin-transactions",
        json={"bin_id": bin_obj.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    bin_txn_id = checkout_r.json()["id"]

    with patch("app.services.telegram_service._send", new=AsyncMock(return_value=None)):
        r = await client.post(
            f"/api/bin-transactions/{bin_txn_id}/return",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200

    result = await db.execute(select(BinTransaction).where(BinTransaction.id == bin_txn_id))
    bin_txn = result.scalar_one()
    assert bin_txn.status == "RETURNED"


# ─── Unlinked user ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unlinked_user_dm_skipped_safely(client: AsyncClient, db: AsyncSession):
    """Checkout for a user with no telegram_chat_id never calls _send for DMs."""
    _, alice, item, _ = await _seed(db)
    assert alice.telegram_chat_id is None

    token = await _login(client, "notif_alice", "alicepass")

    with patch("app.services.telegram_service._send", new=AsyncMock(return_value=1)) as mock_send:
        r = await client.post(
            "/api/transactions/checkout",
            json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 201
    # _send may be called for the coordinator channel but NOT for Alice's DM
    dm_calls = [c for c in mock_send.call_args_list if c.args[0] is None]
    assert not dm_calls, "_send must not be called with None as chat_id"


@pytest.mark.asyncio
async def test_dm_failure_does_not_rollback_db(client: AsyncClient, db: AsyncSession):
    """Even when _send returns None for all calls, the DB transaction is committed."""
    _, alice, item, _ = await _seed(db)
    alice.telegram_chat_id = "alice_persist_test"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    with patch("app.services.telegram_service._send", new=AsyncMock(return_value=None)):
        r = await client.post(
            "/api/transactions/checkout",
            json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 201

    await db.refresh(item)
    assert item.quantity_available == Decimal("4"), "DB quantity must reflect the committed checkout"


# ─── Group-only: low stock ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_low_stock_remains_coordinator_only():
    """notify_low_stock sends to coordinator channel only — no user DM."""
    from app.services import telegram_service

    coordinator_chat_id = "coord_channel_999"

    with patch("app.services.telegram_service.settings") as mock_settings, \
         patch("app.services.telegram_service._send", new=AsyncMock(return_value=1)) as mock_send:

        mock_settings.telegram_coordinator_chat_id = coordinator_chat_id
        mock_settings.telegram_enabled = True

        await telegram_service.notify_low_stock(
            item_name="Widget",
            quantity_available=2,
            threshold=5,
            location="Cabinet A",
        )

    assert mock_send.call_count == 1
    assert mock_send.call_args.args[0] == coordinator_chat_id, "Low stock must only notify coordinator channel"


# ─── Overdue loop isolation ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_overdue_reminder_continues_after_one_user_dm_fails(db: AsyncSession):
    """
    If _send returns None for the first user's DM, the second user's DM is still attempted.
    Verifies that one failed DM does not stop the overdue loop.
    """
    from app.services.telegram_service import notify_overdue

    user_role = _role("OVERDUE_USER")
    db.add(user_role)
    await db.flush()

    user1 = User(
        full_name="Bob", username="bob_overdue",
        password_hash=hash_password("x"), role_id=user_role.id,
        telegram_chat_id="bob_overdue_dm",
    )
    user2 = User(
        full_name="Carol", username="carol_overdue",
        password_hash=hash_password("x"), role_id=user_role.id,
        telegram_chat_id="carol_overdue_dm",
    )
    db.add_all([user1, user2])

    room = Room(name="Overdue Room")
    db.add(room)
    await db.flush()

    cabinet = Cabinet(name="Overdue Cabinet", room_id=room.id)
    db.add(cabinet)
    await db.flush()

    item = Item(
        name="Overdue Widget",
        quantity_total=Decimal("2"),
        quantity_available=Decimal("0"),
        cabinet_id=cabinet.id,
    )
    db.add(item)
    await db.commit()

    for obj in [user1, user2, item]:
        await db.refresh(obj)

    txn1 = Transaction(
        item_id=item.id, user_id=user1.id, processed_by_user_id=user1.id,
        quantity=Decimal("1"), status=TransactionStatus.OVERDUE,
    )
    txn2 = Transaction(
        item_id=item.id, user_id=user2.id, processed_by_user_id=user2.id,
        quantity=Decimal("1"), status=TransactionStatus.OVERDUE,
    )
    db.add_all([txn1, txn2])
    await db.commit()

    for obj in [txn1, txn2]:
        await db.refresh(obj, ["item", "user"])

    dm_chat_ids_called = []

    async def fake_send(chat_id: str, text: str):
        dm_chat_ids_called.append(chat_id)
        return None  # simulate failure for all sends

    with patch("app.services.telegram_service._send", new=AsyncMock(side_effect=fake_send)):
        await notify_overdue(txn1)
        await notify_overdue(txn2)

    assert "bob_overdue_dm" in dm_chat_ids_called, "user1's DM must be attempted"
    assert "carol_overdue_dm" in dm_chat_ids_called, "user2's DM must be attempted even after user1 failed"


# ─── Post-commit exception isolation (Codex BLOCK findings) ──────────────────

@pytest.mark.asyncio
async def test_checkout_item_notification_exception_does_not_500(client: AsyncClient, db: AsyncSession):
    """If notify_checkout raises an unexpected exception, checkout still returns 201 and DB is committed."""
    _, alice, item, _ = await _seed(db)
    alice.telegram_chat_id = "alice_exc_checkout"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    with patch("app.services.telegram_service.notify_checkout", new=AsyncMock(side_effect=RuntimeError("telegram exploded"))):
        r = await client.post(
            "/api/transactions/checkout",
            json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"

    result = await db.execute(select(Transaction).where(Transaction.user_id == alice.id))
    txn = result.scalar_one_or_none()
    assert txn is not None, "Transaction must be committed to DB"
    assert txn.status == TransactionStatus.CHECKED_OUT


@pytest.mark.asyncio
async def test_return_item_notification_exception_does_not_500(client: AsyncClient, db: AsyncSession):
    """If notify_return_and_request_photo raises unexpectedly, return still succeeds and DB is committed."""
    _, alice, item, _ = await _seed(db)
    alice.telegram_chat_id = "alice_exc_return"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    checkout_r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    tx_id = checkout_r.json()["id"]

    with patch(
        "app.services.telegram_service.notify_return_and_request_photo",
        new=AsyncMock(side_effect=RuntimeError("telegram exploded")),
    ):
        r = await client.post(
            f"/api/transactions/{tx_id}/return",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    result = await db.execute(select(Transaction).where(Transaction.id == tx_id))
    txn = result.scalar_one()
    assert txn.status == TransactionStatus.RETURNED, "Return must be committed to DB"


@pytest.mark.asyncio
async def test_checkout_bin_notification_exception_does_not_500(client: AsyncClient, db: AsyncSession):
    """If notify_bin_checkout raises unexpectedly, bin checkout still returns 201 and DB is committed."""
    _, alice, _, bin_obj = await _seed(db)
    alice.telegram_chat_id = "alice_exc_bin_checkout"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    with patch("app.services.telegram_service.notify_bin_checkout", new=AsyncMock(side_effect=RuntimeError("telegram exploded"))):
        r = await client.post(
            "/api/bin-transactions",
            json={"bin_id": bin_obj.id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"

    result = await db.execute(select(BinTransaction).where(BinTransaction.user_id == alice.id))
    bin_txn = result.scalar_one_or_none()
    assert bin_txn is not None, "BinTransaction must be committed to DB"
    assert bin_txn.status == "CHECKED_OUT"


@pytest.mark.asyncio
async def test_return_bin_notification_exception_does_not_500(client: AsyncClient, db: AsyncSession):
    """If notify_bin_return raises unexpectedly, bin return still succeeds and DB is committed."""
    _, alice, _, bin_obj = await _seed(db)
    alice.telegram_chat_id = "alice_exc_bin_return"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    checkout_r = await client.post(
        "/api/bin-transactions",
        json={"bin_id": bin_obj.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    bin_txn_id = checkout_r.json()["id"]

    with patch("app.services.telegram_service.notify_bin_return", new=AsyncMock(side_effect=RuntimeError("telegram exploded"))):
        r = await client.post(
            f"/api/bin-transactions/{bin_txn_id}/return",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    result = await db.execute(select(BinTransaction).where(BinTransaction.id == bin_txn_id))
    bin_txn = result.scalar_one()
    assert bin_txn.status == "RETURNED", "Bin return must be committed to DB"


# ─── Photo-proof message_id preservation ─────────────────────────────────────

@pytest.mark.asyncio
async def test_return_photo_message_id_persisted_if_dm_raises(client: AsyncClient, db: AsyncSession):
    """
    If the coordinator send succeeds but the borrower DM raises, photo_request_message_id
    must still be persisted and the return endpoint must still succeed.
    """
    _, alice, item, _ = await _seed(db)
    alice.telegram_chat_id = "alice_photo_dm_fail"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    checkout_r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    tx_id = checkout_r.json()["id"]

    coordinator_chat = "test_coord_channel"
    coordinator_msg_id = 7777

    def _send_side_effect(chat_id: str, text: str):
        if chat_id == coordinator_chat:
            return coordinator_msg_id  # coordinator send succeeds
        raise RuntimeError("DM send failed")  # borrower DM raises

    with patch("app.services.telegram_service.settings") as mock_settings, \
         patch("app.services.telegram_service._send", new=AsyncMock(side_effect=_send_side_effect)):
        mock_settings.telegram_coordinator_chat_id = coordinator_chat
        mock_settings.telegram_enabled = True

        r = await client.post(
            f"/api/transactions/{tx_id}/return",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200, f"Return must succeed even when DM raises: {r.text}"

    result = await db.execute(select(Transaction).where(Transaction.id == tx_id))
    txn = result.scalar_one()
    assert txn.status == TransactionStatus.RETURNED
    assert txn.photo_request_message_id == str(coordinator_msg_id), (
        f"photo_request_message_id must be persisted even when borrower DM raises, got: {txn.photo_request_message_id}"
    )


# ─── Coordinator notification presence ───────────────────────────────────────

@pytest.mark.asyncio
async def test_coordinator_notified_on_item_checkout(client: AsyncClient, db: AsyncSession):
    """Item checkout sends coordinator notification as well as user DM."""
    _, alice, item, _ = await _seed(db)
    alice.telegram_chat_id = "alice_coord_check"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    coordinator_chat = "test_coord_chan"
    calls = []

    async def capture_send(chat_id, text):
        calls.append(chat_id)
        return 1

    with patch("app.services.telegram_service.settings") as mock_settings, \
         patch("app.services.telegram_service._send", new=AsyncMock(side_effect=capture_send)):
        mock_settings.telegram_coordinator_chat_id = coordinator_chat
        mock_settings.telegram_enabled = True

        r = await client.post(
            "/api/transactions/checkout",
            json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 201
    assert coordinator_chat in calls, "Coordinator channel must be notified on item checkout"
    assert "alice_coord_check" in calls, "Borrower must receive a DM on item checkout"


@pytest.mark.asyncio
async def test_coordinator_notified_on_bin_checkout(client: AsyncClient, db: AsyncSession):
    """Bin checkout sends coordinator notification as well as user DM."""
    _, alice, _, bin_obj = await _seed(db)
    alice.telegram_chat_id = "alice_bin_coord_check"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    coordinator_chat = "test_bin_coord_chan"
    calls = []

    async def capture_send(chat_id, text):
        calls.append(chat_id)
        return 1

    with patch("app.services.telegram_service.settings") as mock_settings, \
         patch("app.services.telegram_service._send", new=AsyncMock(side_effect=capture_send)):
        mock_settings.telegram_coordinator_chat_id = coordinator_chat
        mock_settings.telegram_enabled = True

        r = await client.post(
            "/api/bin-transactions",
            json={"bin_id": bin_obj.id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 201
    assert coordinator_chat in calls, "Coordinator channel must be notified on bin checkout"
    assert "alice_bin_coord_check" in calls, "Borrower must receive a DM on bin checkout"


# ─── send_user_dm unexpected exception ───────────────────────────────────────

@pytest.mark.asyncio
async def test_send_user_dm_returns_false_on_unexpected_exception():
    """send_user_dm returns False and does not raise when _send raises a non-Telegram exception."""
    from unittest.mock import MagicMock
    from app.services.telegram_service import send_user_dm

    user = MagicMock()
    user.telegram_chat_id = "some_chat_id"
    user.id = 42

    with patch("app.services.telegram_service._send", new=AsyncMock(side_effect=RuntimeError("network error"))):
        result = await send_user_dm(user, "test message")

    assert result is False, "send_user_dm must return False when _send raises unexpectedly"


@pytest.mark.asyncio
async def test_send_user_dm_returns_false_for_none_user():
    """send_user_dm returns False and does not raise when user is None."""
    from app.services.telegram_service import send_user_dm

    result = await send_user_dm(None, "test message")  # type: ignore[arg-type]
    assert result is False


# ─── _send get_bot failure isolation ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_returns_none_when_get_bot_raises():
    """_send returns None and does not raise when get_bot raises during bot construction."""
    from app.services import telegram_service

    with patch("app.services.telegram_service.get_bot", side_effect=RuntimeError("bot init failed")):
        result = await telegram_service._send("some_chat_id", "hello")

    assert result is None, "_send must return None when get_bot raises"


# ─── Photo-proof state consistency when coordinator send fails ────────────────

@pytest.mark.asyncio
async def test_return_photo_state_cleared_when_coordinator_send_returns_none(
    client: AsyncClient, db: AsyncSession
):
    """
    When the coordinator photo-request _send returns None, the return still
    succeeds and photo_requested_via_telegram is cleared — no unmatchable state.
    """
    _, alice, item, _ = await _seed(db)
    alice.telegram_chat_id = "alice_photo_coord_fail"
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    checkout_r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    tx_id = checkout_r.json()["id"]

    with patch("app.services.telegram_service.settings") as mock_settings, \
         patch("app.services.telegram_service._send", new=AsyncMock(return_value=None)):
        mock_settings.telegram_coordinator_chat_id = "test_coord_fail_channel"
        mock_settings.telegram_enabled = True

        r = await client.post(
            f"/api/transactions/{tx_id}/return",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200, f"Return must succeed when coordinator send returns None: {r.text}"

    result = await db.execute(select(Transaction).where(Transaction.id == tx_id))
    txn = result.scalar_one()
    assert txn.status == TransactionStatus.RETURNED
    assert txn.photo_request_message_id is None
    assert txn.photo_requested_via_telegram is False, (
        "photo_requested_via_telegram must be cleared when coordinator send returns None"
    )


@pytest.mark.asyncio
async def test_return_photo_state_cleared_when_notify_raises(
    client: AsyncClient, db: AsyncSession
):
    """
    When notify_return_and_request_photo raises entirely, the return still
    succeeds and photo_requested_via_telegram is cleared — no unmatchable state.
    """
    _, alice, item, _ = await _seed(db)
    await db.commit()

    token = await _login(client, "notif_alice", "alicepass")

    checkout_r = await client.post(
        "/api/transactions/checkout",
        json={"item_id": item.id, "user_id": alice.id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    tx_id = checkout_r.json()["id"]

    with patch(
        "app.services.telegram_service.notify_return_and_request_photo",
        new=AsyncMock(side_effect=RuntimeError("notification system down")),
    ):
        r = await client.post(
            f"/api/transactions/{tx_id}/return",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200, f"Return must succeed when notify raises: {r.text}"

    result = await db.execute(select(Transaction).where(Transaction.id == tx_id))
    txn = result.scalar_one()
    assert txn.status == TransactionStatus.RETURNED
    assert txn.photo_request_message_id is None
    assert txn.photo_requested_via_telegram is False, (
        "photo_requested_via_telegram must be cleared when notify_return_and_request_photo raises"
    )
