import logging
import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user as get_current_active_user, get_db
from app.core.permissions import require_manage_inventory
from app.models.item import Item
from app.models.purchase_record import PurchaseRecord
from app.models.receipt_record import ReceiptRecord
from app.models.user import User
from app.schemas.purchase import PurchaseRecordCreate, PurchaseRecordOut, ReceiptRecordOut
from app.services.purchase_service import create_receipt, log_purchase
from app.services import telegram_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/purchases", tags=["purchases"])

RECEIPT_UPLOAD_DIR = os.environ.get("RECEIPT_UPLOAD_DIR", "/tmp/receipts")


@router.post("", response_model=PurchaseRecordOut, status_code=201)
async def create_purchase(
    body: PurchaseRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manage_inventory(current_user)

    purchase = await log_purchase(
        db,
        item_id=body.item_id,
        purchased_by_user_id=current_user.id,
        quantity_purchased=body.quantity_purchased,
        unit_price=body.unit_price,
        total_price=body.total_price,
        vendor=body.vendor,
        notes=body.notes,
        receipt_id=body.receipt_id,
    )

    # Create a placeholder ReceiptRecord now so we have a receipt_id to attach the
    # Telegram photo reply to later. The record starts with no file — it gets
    # populated when the purchaser replies with a photo in Telegram.
    if not body.receipt_id:
        placeholder = ReceiptRecord(
            uploaded_by_user_id=current_user.id,
            uploaded_via="telegram",
            notes="Awaiting receipt via Telegram",
        )
        db.add(placeholder)
        await db.flush()
        purchase.receipt_id = placeholder.id
    else:
        placeholder = None

    await db.commit()
    await db.refresh(purchase)

    # Fetch item name for notification
    item_result = await db.execute(select(Item).where(Item.id == body.item_id))
    item = item_result.scalar_one_or_none()
    item_name = item.name if item else f"Item #{body.item_id}"

    # Fire-and-forget Telegram notification (group + DM)
    msg_id = await telegram_service.notify_purchase_and_request_receipt(
        purchase_id=purchase.id,
        item_name=item_name,
        quantity=body.quantity_purchased,
        purchaser_name=current_user.username,
        purchaser_tg_handle=current_user.telegram_handle,
        purchaser_chat_id=current_user.telegram_chat_id,
    )

    # Store the coordinator channel message_id so the bot can match photo replies
    if msg_id and placeholder is not None:
        placeholder_result = await db.execute(
            select(ReceiptRecord).where(ReceiptRecord.id == purchase.receipt_id)
        )
        rec = placeholder_result.scalar_one_or_none()
        if rec:
            rec.telegram_request_message_id = msg_id
            await db.commit()

    return purchase


@router.get("/item/{item_id}", response_model=List[PurchaseRecordOut])
async def list_purchases_for_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manage_inventory(current_user)
    result = await db.execute(
        select(PurchaseRecord)
        .where(PurchaseRecord.item_id == item_id)
        .order_by(PurchaseRecord.purchased_at.desc())
    )
    return result.scalars().all()


@router.post("/receipts", response_model=ReceiptRecordOut, status_code=201)
async def upload_receipt(
    file: UploadFile = File(...),
    total_amount: float | None = Form(None),
    vendor: str | None = Form(None),
    notes: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Upload a receipt image directly via the web app (rare path — Telegram is primary)."""
    require_manage_inventory(current_user)

    os.makedirs(RECEIPT_UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename or "receipt")[1]
    file_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(RECEIPT_UPLOAD_DIR, file_name)

    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    receipt = await create_receipt(
        db,
        uploaded_by_user_id=current_user.id,
        file_path=file_path,
        file_name=file.filename,
        mime_type=file.content_type,
        total_amount=total_amount,
        vendor=vendor,
        notes=notes,
        uploaded_via="web",
    )
    await db.commit()
    await db.refresh(receipt)
    return receipt


@router.get("/receipts/{receipt_id}", response_model=ReceiptRecordOut)
async def get_receipt(
    receipt_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manage_inventory(current_user)
    result = await db.execute(select(ReceiptRecord).where(ReceiptRecord.id == receipt_id))
    receipt = result.scalar_one_or_none()
    if not receipt:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receipt not found")
    return receipt
