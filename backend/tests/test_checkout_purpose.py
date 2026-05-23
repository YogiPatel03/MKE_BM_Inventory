"""
Tests proving that checkout purpose defaults to GENERAL on both Transaction
and BinTransaction when not explicitly provided, and that Sabha checklist
return tasks are created only for SABHA checkouts.
"""

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import select

from app.core.security import hash_password
from app.dependencies import get_current_user
from app.main import app
from app.models.bin import Bin
from app.models.bin_transaction import BinTransaction, BinTransactionStatus
from app.models.cabinet import Cabinet
from app.models.checklist import ChecklistItem, GroupName
from app.models.item import Item
from app.models.role import Role
from app.models.room import Room
from app.models.transaction import CheckoutPurpose, Transaction, TransactionStatus
from app.models.user import User
from app.schemas.bin_transaction import BinTransactionCreate, BinTransactionOut
from app.schemas.transaction import CheckoutRequest, TransactionOut
from app.services.checklist_service import (
    add_return_task_for_bin_transaction,
    add_return_task_for_transaction,
)
from app.services.bin_transaction_service import checkout_bin
from app.services.transaction_service import checkout_item


# ── Schema default tests ───────────────────────────────────────────────────────

def test_checkout_request_purpose_defaults_to_general():
    req = CheckoutRequest(item_id=1, user_id=2)
    assert req.purpose == "GENERAL"


def test_checkout_request_accepts_sabha_purpose():
    req = CheckoutRequest(item_id=1, user_id=2, purpose="SABHA")
    assert req.purpose == "SABHA"


def test_checkout_request_without_purpose_field_passes_validation():
    """Existing API payloads that omit purpose must still be valid."""
    data = {"item_id": 1, "user_id": 2, "quantity": 1.0}
    req = CheckoutRequest(**data)
    assert req.purpose == "GENERAL"


def test_bin_transaction_create_purpose_defaults_to_general():
    body = BinTransactionCreate(bin_id=5)
    assert body.purpose == "GENERAL"


def test_bin_transaction_create_accepts_sabha_purpose():
    body = BinTransactionCreate(bin_id=5, purpose="SABHA")
    assert body.purpose == "SABHA"


def test_bin_transaction_create_without_purpose_passes_validation():
    """Existing API payloads that omit purpose must still be valid."""
    data = {"bin_id": 5}
    body = BinTransactionCreate(**data)
    assert body.purpose == "GENERAL"


# ── CheckoutPurpose enum ───────────────────────────────────────────────────────

def test_checkout_purpose_values():
    assert CheckoutPurpose.GENERAL == "GENERAL"
    assert CheckoutPurpose.SABHA == "SABHA"


def test_checkout_purpose_is_str_enum():
    assert isinstance(CheckoutPurpose.GENERAL, str)
    assert isinstance(CheckoutPurpose.SABHA, str)


# ── ORM model default tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_transaction_orm_default_purpose(db):
    from app.models.item import Item
    from app.models.role import Role
    from app.models.user import User
    from app.models.cabinet import Cabinet
    from app.models.room import Room

    role = Role(name="member")
    db.add(role)
    await db.flush()

    room = Room(name="Test Room")
    db.add(room)
    await db.flush()

    cabinet = Cabinet(name="Test Cabinet", room_id=room.id)
    db.add(cabinet)
    await db.flush()

    user = User(username="testuser", full_name="Test User", role_id=role.id, password_hash="x")
    db.add(user)
    await db.flush()

    item = Item(name="Widget", quantity_total=10, quantity_available=10, cabinet_id=cabinet.id)
    db.add(item)
    await db.flush()

    txn = Transaction(
        item_id=item.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        quantity=1,
        status=TransactionStatus.CHECKED_OUT,
    )
    db.add(txn)
    await db.flush()
    await db.refresh(txn)

    assert txn.purpose == CheckoutPurpose.GENERAL


@pytest.mark.asyncio
async def test_bin_transaction_orm_default_purpose(db):
    from app.models.bin import Bin
    from app.models.cabinet import Cabinet
    from app.models.role import Role
    from app.models.room import Room
    from app.models.user import User

    role = Role(name="member2")
    db.add(role)
    await db.flush()

    room = Room(name="Bin Room")
    db.add(room)
    await db.flush()

    cabinet = Cabinet(name="Bin Cabinet", room_id=room.id)
    db.add(cabinet)
    await db.flush()

    user = User(username="binuser", full_name="Bin User", role_id=role.id, password_hash="x")
    db.add(user)
    await db.flush()

    bin_ = Bin(label="BIN-001", cabinet_id=cabinet.id)
    db.add(bin_)
    await db.flush()

    bin_txn = BinTransaction(
        bin_id=bin_.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        status=BinTransactionStatus.CHECKED_OUT,
    )
    db.add(bin_txn)
    await db.flush()
    await db.refresh(bin_txn)

    assert bin_txn.purpose == CheckoutPurpose.GENERAL


# ── Helpers for checklist behavior tests ──────────────────────────────────────

async def _make_full_env(db, username: str, group_name: str = GroupName.GROUP_1):
    """Create role, user with group, room, cabinet, item, and bin with one item."""
    role = Role(
        name=f"role_{username}",
        can_process_any_transaction=True,
        can_view_all_transactions=True,
    )
    db.add(role)
    await db.flush()

    user = User(
        username=username,
        full_name="Test User",
        password_hash=hash_password("pass"),
        role_id=role.id,
        group_name=group_name,
    )
    db.add(user)
    await db.flush()

    room = Room(name=f"room_{username}")
    db.add(room)
    await db.flush()

    cabinet = Cabinet(name=f"cabinet_{username}", room_id=room.id)
    db.add(cabinet)
    await db.flush()

    item = Item(
        name=f"item_{username}",
        quantity_total=5,
        quantity_available=5,
        cabinet_id=cabinet.id,
    )
    db.add(item)
    await db.flush()

    bin_ = Bin(label=f"BIN-{username}", cabinet_id=cabinet.id)
    db.add(bin_)
    await db.flush()

    bin_item = Item(
        name=f"binitem_{username}",
        quantity_total=3,
        quantity_available=3,
        cabinet_id=cabinet.id,
        bin_id=bin_.id,
    )
    db.add(bin_item)
    await db.flush()

    return user, item, bin_, bin_item


async def _count_auto_tasks(db) -> int:
    result = await db.execute(
        select(ChecklistItem).where(ChecklistItem.is_auto_generated == True)
    )
    return len(result.scalars().all())


# ── 1. Item GENERAL: no checklist return task ──────────────────────────────────

@pytest.mark.asyncio
async def test_item_checkout_general_creates_no_checklist_task(db):
    user, item, _, _ = await _make_full_env(db, "gen_item1")

    txn = await checkout_item(
        db,
        item_id=item.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        quantity=1,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.GENERAL,
    )
    result, created = await add_return_task_for_transaction(db, txn, user)

    assert result is None
    assert created is False
    assert await _count_auto_tasks(db) == 0


# ── 2. Item SABHA: return task created ────────────────────────────────────────

@pytest.mark.asyncio
async def test_item_checkout_sabha_creates_checklist_task(db):
    user, item, _, _ = await _make_full_env(db, "sabha_item1")

    txn = await checkout_item(
        db,
        item_id=item.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        quantity=1,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.SABHA,
    )
    result, created = await add_return_task_for_transaction(db, txn, user)

    assert result is not None
    assert created is True
    assert result.auto_type == "ITEM_RETURN"
    assert result.linked_transaction_id == txn.id
    assert await _count_auto_tasks(db) == 1


# ── 3. Item missing purpose → GENERAL, no task ────────────────────────────────

@pytest.mark.asyncio
async def test_item_checkout_default_purpose_creates_no_checklist_task(db):
    user, item, _, _ = await _make_full_env(db, "default_item1")

    txn = await checkout_item(
        db,
        item_id=item.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        quantity=1,
        due_at=None,
        notes=None,
        # purpose omitted → defaults to GENERAL
    )
    assert txn.purpose == CheckoutPurpose.GENERAL

    result, created = await add_return_task_for_transaction(db, txn, user)
    assert result is None
    assert created is False
    assert await _count_auto_tasks(db) == 0


# ── 4. Bin GENERAL: no checklist return task ──────────────────────────────────

@pytest.mark.asyncio
async def test_bin_checkout_general_creates_no_checklist_task(db):
    user, _, bin_, _ = await _make_full_env(db, "gen_bin1")

    bin_txn, _ = await checkout_bin(
        db,
        bin_id=bin_.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.GENERAL,
    )
    result, created = await add_return_task_for_bin_transaction(db, bin_txn, user)

    assert result is None
    assert created is False
    assert await _count_auto_tasks(db) == 0


# ── 5. Bin SABHA: return task created ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_bin_checkout_sabha_creates_checklist_task(db):
    user, _, bin_, _ = await _make_full_env(db, "sabha_bin1")

    bin_txn, _ = await checkout_bin(
        db,
        bin_id=bin_.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.SABHA,
    )
    result, created = await add_return_task_for_bin_transaction(db, bin_txn, user)

    assert result is not None
    assert created is True
    assert result.auto_type == "BIN_RETURN"
    assert result.linked_bin_transaction_id == bin_txn.id
    assert await _count_auto_tasks(db) == 1


# ── 6. Bin missing purpose → GENERAL, no task ─────────────────────────────────

@pytest.mark.asyncio
async def test_bin_checkout_default_purpose_creates_no_checklist_task(db):
    user, _, bin_, _ = await _make_full_env(db, "default_bin1")

    bin_txn, _ = await checkout_bin(
        db,
        bin_id=bin_.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        due_at=None,
        notes=None,
        # purpose omitted → defaults to GENERAL
    )
    assert bin_txn.purpose == CheckoutPurpose.GENERAL

    result, created = await add_return_task_for_bin_transaction(db, bin_txn, user)
    assert result is None
    assert created is False
    assert await _count_auto_tasks(db) == 0


# ── 7. Bin child transactions inherit GENERAL ─────────────────────────────────

@pytest.mark.asyncio
async def test_bin_child_transactions_inherit_general_purpose(db):
    user, _, bin_, bin_item = await _make_full_env(db, "gen_child1")

    bin_txn, _ = await checkout_bin(
        db,
        bin_id=bin_.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.GENERAL,
    )

    child_txns = (await db.execute(
        select(Transaction).where(Transaction.bin_transaction_id == bin_txn.id)
    )).scalars().all()

    assert len(child_txns) >= 1
    for child in child_txns:
        assert child.purpose == CheckoutPurpose.GENERAL


# ── 8. Bin child transactions inherit SABHA ───────────────────────────────────

@pytest.mark.asyncio
async def test_bin_child_transactions_inherit_sabha_purpose(db):
    user, _, bin_, bin_item = await _make_full_env(db, "sabha_child1")

    bin_txn, _ = await checkout_bin(
        db,
        bin_id=bin_.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.SABHA,
    )

    child_txns = (await db.execute(
        select(Transaction).where(Transaction.bin_transaction_id == bin_txn.id)
    )).scalars().all()

    assert len(child_txns) >= 1
    for child in child_txns:
        assert child.purpose == CheckoutPurpose.SABHA


# ── 9. Return a SABHA item: auto-completes the return task ────────────────────

@pytest.mark.asyncio
async def test_sabha_item_return_auto_completes_checklist_task(db):
    from app.services.checklist_service import auto_complete_return_task_for_transaction

    user, item, _, _ = await _make_full_env(db, "return_sabha1")

    txn = await checkout_item(
        db,
        item_id=item.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        quantity=1,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.SABHA,
    )
    task, created = await add_return_task_for_transaction(db, txn, user)
    assert task is not None
    assert created is True
    assert task.is_completed is False

    completed_task = await auto_complete_return_task_for_transaction(db, txn.id, user.id)
    assert completed_task is not None
    assert completed_task.is_completed is True
    assert completed_task.id == task.id


# ── Issue 2: Schema-level rejection of invalid purpose values ─────────────────

def test_checkout_request_rejects_invalid_purpose():
    with pytest.raises(ValidationError):
        CheckoutRequest(item_id=1, user_id=2, purpose="random")


def test_checkout_request_rejects_lowercase_sabha():
    with pytest.raises(ValidationError):
        CheckoutRequest(item_id=1, user_id=2, purpose="sabha")


def test_checkout_request_rejects_whitespace_purpose():
    with pytest.raises(ValidationError):
        CheckoutRequest(item_id=1, user_id=2, purpose="SABHA ")


def test_bin_transaction_create_rejects_invalid_purpose():
    with pytest.raises(ValidationError):
        BinTransactionCreate(bin_id=5, purpose="random")


def test_bin_transaction_create_rejects_lowercase_sabha():
    with pytest.raises(ValidationError):
        BinTransactionCreate(bin_id=5, purpose="sabha")


def test_bin_transaction_create_rejects_whitespace_purpose():
    with pytest.raises(ValidationError):
        BinTransactionCreate(bin_id=5, purpose="SABHA ")


def test_checkout_request_missing_purpose_defaults_to_general():
    req = CheckoutRequest(item_id=1, user_id=2)
    assert req.purpose == CheckoutPurpose.GENERAL


def test_bin_transaction_create_missing_purpose_defaults_to_general():
    body = BinTransactionCreate(bin_id=5)
    assert body.purpose == CheckoutPurpose.GENERAL


# ── Issue 3: Backfill created/skipped counts ──────────────────────────────────

from httpx import AsyncClient, ASGITransport
from app.dependencies import get_db


@pytest_asyncio.fixture
async def admin_client(db):
    """Client authenticated as an admin user."""
    from app.models.role import Role
    from app.models.user import User
    from app.dependencies import get_current_user

    admin_role = Role(
        name="backfill_admin",
        can_manage_inventory=True,
        can_manage_users=True,
        can_process_any_transaction=True,
        can_view_all_transactions=True,
        can_approve_requests=True,
    )
    db.add(admin_role)
    await db.flush()

    admin = User(
        username="backfill_admin_user",
        full_name="Backfill Admin",
        password_hash="x",
        role_id=admin_role.id,
    )
    db.add(admin)
    await db.flush()

    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_backfill_general_transaction_reports_skipped(db, admin_client):
    """GENERAL checkout: backfill endpoint reports skipped=1, created=0."""
    user, item, _, _ = await _make_full_env(db, "backfill_gen1")

    txn = await checkout_item(
        db,
        item_id=item.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        quantity=1,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.GENERAL,
    )
    await db.flush()

    r = await admin_client.post("/api/checklists/backfill-active-transactions")
    assert r.status_code == 200
    data = r.json()
    assert data["created"] == 0
    assert data["skipped"] >= 1
    assert await _count_auto_tasks(db) == 0


@pytest.mark.asyncio
async def test_backfill_sabha_transaction_reports_created(db, admin_client):
    """SABHA checkout: backfill endpoint reports created=1, creates a task."""
    user, item, _, _ = await _make_full_env(db, "backfill_sabha1")

    txn = await checkout_item(
        db,
        item_id=item.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        quantity=1,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.SABHA,
    )
    await db.flush()

    r = await admin_client.post("/api/checklists/backfill-active-transactions")
    assert r.status_code == 200
    data = r.json()
    assert data["created"] >= 1
    assert await _count_auto_tasks(db) >= 1


@pytest.mark.asyncio
async def test_backfill_mixed_general_and_sabha_counts(db, admin_client):
    """Mixed GENERAL + SABHA: backfill reports accurate created/skipped split."""
    user1, item1, _, _ = await _make_full_env(db, "backfill_mixed_g")
    user2, item2, _, _ = await _make_full_env(db, "backfill_mixed_s")

    await checkout_item(
        db,
        item_id=item1.id,
        user_id=user1.id,
        processed_by_user_id=user1.id,
        quantity=1,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.GENERAL,
    )
    await checkout_item(
        db,
        item_id=item2.id,
        user_id=user2.id,
        processed_by_user_id=user2.id,
        quantity=1,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.SABHA,
    )
    await db.flush()

    r = await admin_client.post("/api/checklists/backfill-active-transactions")
    assert r.status_code == 200
    data = r.json()
    assert data["created"] >= 1
    assert data["skipped"] >= 1
    assert await _count_auto_tasks(db) >= 1


# ── Idempotency tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_return_task_for_transaction_is_idempotent(db):
    """Calling add_return_task_for_transaction twice for the same SABHA transaction
    must return the same task and not create a duplicate."""
    user, item, _, _ = await _make_full_env(db, "idem_txn1")

    txn = await checkout_item(
        db,
        item_id=item.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        quantity=1,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.SABHA,
    )

    task1, created1 = await add_return_task_for_transaction(db, txn, user)
    task2, created2 = await add_return_task_for_transaction(db, txn, user)

    assert task1 is not None
    assert task2 is not None
    assert task1.id == task2.id
    assert created1 is True
    assert created2 is False  # second call returns existing, not new
    assert await _count_auto_tasks(db) == 1


@pytest.mark.asyncio
async def test_add_return_task_for_bin_transaction_is_idempotent(db):
    """Calling add_return_task_for_bin_transaction twice for the same SABHA bin
    checkout must return the same task and not create a duplicate."""
    user, _, bin_, _ = await _make_full_env(db, "idem_bin1")

    bin_txn, _ = await checkout_bin(
        db,
        bin_id=bin_.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.SABHA,
    )

    task1, created1 = await add_return_task_for_bin_transaction(db, bin_txn, user)
    task2, created2 = await add_return_task_for_bin_transaction(db, bin_txn, user)

    assert task1 is not None
    assert task2 is not None
    assert task1.id == task2.id
    assert created1 is True
    assert created2 is False  # second call returns existing, not new
    assert await _count_auto_tasks(db) == 1


@pytest.mark.asyncio
async def test_backfill_run_twice_creates_no_duplicates(db, admin_client):
    """Running the backfill endpoint twice for the same SABHA transaction must
    create exactly one task, not two."""
    user, item, _, _ = await _make_full_env(db, "idem_backfill1")

    await checkout_item(
        db,
        item_id=item.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        quantity=1,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.SABHA,
    )
    await db.flush()

    r1 = await admin_client.post("/api/checklists/backfill-active-transactions")
    assert r1.status_code == 200
    assert r1.json()["created"] >= 1

    r2 = await admin_client.post("/api/checklists/backfill-active-transactions")
    assert r2.status_code == 200
    assert r2.json()["created"] == 0

    assert await _count_auto_tasks(db) == 1


@pytest.mark.asyncio
async def test_general_transaction_still_creates_no_task_after_idempotency_fix(db):
    """GENERAL checkouts must still produce no return task (regression guard)."""
    user, item, _, _ = await _make_full_env(db, "idem_general1")

    txn = await checkout_item(
        db,
        item_id=item.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        quantity=1,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.GENERAL,
    )

    result1, _ = await add_return_task_for_transaction(db, txn, user)
    result2, _ = await add_return_task_for_transaction(db, txn, user)

    assert result1 is None
    assert result2 is None
    assert await _count_auto_tasks(db) == 0


@pytest.mark.asyncio
async def test_sabha_return_task_completion_still_works_after_idempotency_fix(db):
    """Return task auto-completion must still work correctly (regression guard)."""
    from app.services.checklist_service import auto_complete_return_task_for_transaction

    user, item, _, _ = await _make_full_env(db, "idem_complete1")

    txn = await checkout_item(
        db,
        item_id=item.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        quantity=1,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.SABHA,
    )
    task, _ = await add_return_task_for_transaction(db, txn, user)
    # Second call must return same task
    task_again, _ = await add_return_task_for_transaction(db, txn, user)
    assert task is not None and task_again is not None
    assert task.id == task_again.id

    completed = await auto_complete_return_task_for_transaction(db, txn.id, user.id)
    assert completed is not None
    assert completed.is_completed is True
    assert completed.id == task.id


# ── Backfill bin-path tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_backfill_sabha_bin_creates_bin_return_not_item_return(db, admin_client):
    """SABHA bin checkout: backfill creates exactly one BIN_RETURN task and zero
    ITEM_RETURN tasks for the child transactions."""
    user, _, bin_, _ = await _make_full_env(db, "bf_bin_sabha1")

    await checkout_bin(
        db,
        bin_id=bin_.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.SABHA,
    )
    await db.flush()

    r = await admin_client.post("/api/checklists/backfill-active-transactions")
    assert r.status_code == 200
    data = r.json()
    assert data["created"] == 1

    # Exactly one auto-generated task and it must be a BIN_RETURN, not ITEM_RETURN.
    result = await db.execute(
        select(ChecklistItem).where(ChecklistItem.is_auto_generated == True)
    )
    tasks = result.scalars().all()
    assert len(tasks) == 1
    assert tasks[0].auto_type == "BIN_RETURN"
    assert tasks[0].linked_bin_transaction_id is not None
    assert tasks[0].linked_transaction_id is None


@pytest.mark.asyncio
async def test_backfill_sabha_bin_with_existing_task_counts_as_skipped(db, admin_client):
    """SABHA bin checkout with an existing BIN_RETURN task: backfill skips it,
    created=0, and does not create a duplicate."""
    user, _, bin_, _ = await _make_full_env(db, "bf_bin_exist1")

    bin_txn, _ = await checkout_bin(
        db,
        bin_id=bin_.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.SABHA,
    )
    await db.flush()

    # Pre-create the task so backfill finds it as existing.
    await add_return_task_for_bin_transaction(db, bin_txn, user)
    await db.flush()

    r = await admin_client.post("/api/checklists/backfill-active-transactions")
    assert r.status_code == 200
    data = r.json()
    assert data["created"] == 0
    assert data["skipped"] >= 1

    # Still only one task.
    result = await db.execute(
        select(ChecklistItem).where(ChecklistItem.is_auto_generated == True)
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_backfill_general_bin_creates_no_task(db, admin_client):
    """GENERAL bin checkout: backfill creates no return task."""
    user, _, bin_, _ = await _make_full_env(db, "bf_bin_gen1")

    await checkout_bin(
        db,
        bin_id=bin_.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.GENERAL,
    )
    await db.flush()

    r = await admin_client.post("/api/checklists/backfill-active-transactions")
    assert r.status_code == 200
    data = r.json()
    assert data["created"] == 0
    assert await _count_auto_tasks(db) == 0


@pytest.mark.asyncio
async def test_backfill_mixed_item_and_bin_sabha(db, admin_client):
    """Mixed SABHA item checkout + SABHA bin checkout: backfill creates one
    ITEM_RETURN for the standalone item and one BIN_RETURN for the bin.
    Child transactions from the bin checkout are excluded from the item path."""
    user1, item1, _, _ = await _make_full_env(db, "bf_mix_item1")
    user2, _, bin2, _ = await _make_full_env(db, "bf_mix_bin1")

    # Standalone SABHA item checkout.
    await checkout_item(
        db,
        item_id=item1.id,
        user_id=user1.id,
        processed_by_user_id=user1.id,
        quantity=1,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.SABHA,
    )
    # SABHA bin checkout — creates child Transaction rows with bin_transaction_id set.
    await checkout_bin(
        db,
        bin_id=bin2.id,
        user_id=user2.id,
        processed_by_user_id=user2.id,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.SABHA,
    )
    await db.flush()

    r = await admin_client.post("/api/checklists/backfill-active-transactions")
    assert r.status_code == 200
    data = r.json()
    assert data["created"] == 2  # one ITEM_RETURN + one BIN_RETURN

    result = await db.execute(
        select(ChecklistItem).where(ChecklistItem.is_auto_generated == True)
    )
    tasks = result.scalars().all()
    auto_types = {t.auto_type for t in tasks}
    assert "ITEM_RETURN" in auto_types
    assert "BIN_RETURN" in auto_types
    assert len(tasks) == 2


@pytest.mark.asyncio
async def test_backfill_bin_child_transactions_excluded_from_item_path(db, admin_client):
    """Child Transaction rows (bin_transaction_id IS NOT NULL) must not produce
    ITEM_RETURN tasks during backfill, even when their purpose is SABHA."""
    user, _, bin_, _ = await _make_full_env(db, "bf_excl1")

    await checkout_bin(
        db,
        bin_id=bin_.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.SABHA,
    )
    await db.flush()

    r = await admin_client.post("/api/checklists/backfill-active-transactions")
    assert r.status_code == 200

    result = await db.execute(
        select(ChecklistItem).where(
            ChecklistItem.is_auto_generated == True,
            ChecklistItem.auto_type == "ITEM_RETURN",
        )
    )
    item_return_tasks = result.scalars().all()
    assert len(item_return_tasks) == 0, (
        "Bin child transactions must not produce ITEM_RETURN tasks"
    )


@pytest.mark.asyncio
async def test_backfill_bin_run_twice_is_idempotent(db, admin_client):
    """Running backfill twice for a SABHA bin checkout must create exactly one
    BIN_RETURN task total; the second run must not create a duplicate."""
    user, _, bin_, _ = await _make_full_env(db, "bf_bin_idem1")

    await checkout_bin(
        db,
        bin_id=bin_.id,
        user_id=user.id,
        processed_by_user_id=user.id,
        due_at=None,
        notes=None,
        purpose=CheckoutPurpose.SABHA,
    )
    await db.flush()

    r1 = await admin_client.post("/api/checklists/backfill-active-transactions")
    assert r1.status_code == 200
    assert r1.json()["created"] == 1

    r2 = await admin_client.post("/api/checklists/backfill-active-transactions")
    assert r2.status_code == 200
    assert r2.json()["created"] == 0

    assert await _count_auto_tasks(db) == 1
