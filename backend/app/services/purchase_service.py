"""
Purchase and receipt service — log restocking events with pricing history.
"""

import logging
import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.activity_log import ActivityType
from app.models.item import Item
from app.models.purchase_record import PurchaseRecord
from app.models.receipt_record import ReceiptRecord
from app.services.activity_service import log_activity
from app.services.restock_service import restore_from_restock_if_nonzero

log = logging.getLogger(__name__)

RECEIPT_UPLOAD_DIR = os.environ.get("RECEIPT_UPLOAD_DIR", "/tmp/receipts")


async def log_purchase(
    db: AsyncSession,
    *,
    item_id: int,
    purchased_by_user_id: int,
    quantity_purchased: int,
    unit_price: Optional[float],
    total_price: Optional[float],
    vendor: Optional[str],
    notes: Optional[str],
    receipt_id: Optional[int],
) -> PurchaseRecord:
    result = await db.execute(
        select(Item).where(Item.id == item_id, Item.is_active == True).with_for_update()
    )
    item = result.scalar_one_or_none()
    if not item:
        raise NotFoundError("Item", item_id)

    # Restock: add to total and available
    item.quantity_total += quantity_purchased
    item.quantity_available += quantity_purchased

    # Update current unit price
    if unit_price is not None:
        item.unit_price = unit_price

    purchase = PurchaseRecord(
        item_id=item_id,
        purchased_by_user_id=purchased_by_user_id,
        quantity_purchased=quantity_purchased,
        unit_price=unit_price,
        total_price=total_price,
        vendor=vendor,
        notes=notes,
        receipt_id=receipt_id,
    )
    db.add(purchase)
    await db.flush()
    await db.refresh(purchase)

    cost_impact = total_price or (unit_price * quantity_purchased if unit_price else None)
    await log_activity(
        db,
        activity_type=ActivityType.PURCHASE_LOGGED,
        actor_id=purchased_by_user_id,
        target_item_id=item_id,
        target_cabinet_id=item.cabinet_id,
        quantity_delta=+quantity_purchased,
        cost_impact=cost_impact,
        notes=notes,
        metadata={"vendor": vendor, "unit_price": unit_price, "total_price": total_price},
        source_type="purchase_record",
        source_id=purchase.id,
    )

    # Restore from Restock Me if restocking brought stock > 0
    await restore_from_restock_if_nonzero(db, item, actor_id=purchased_by_user_id)

    log.info("Purchase: purchase=%d item=%d qty=%d", purchase.id, item_id, quantity_purchased)
    return purchase


async def create_receipt(
    db: AsyncSession,
    *,
    uploaded_by_user_id: Optional[int],
    file_path: Optional[str],
    file_name: Optional[str],
    mime_type: Optional[str],
    total_amount: Optional[float],
    vendor: Optional[str],
    notes: Optional[str],
    uploaded_via: str = "web",
    telegram_request_message_id: Optional[str] = None,
) -> ReceiptRecord:
    receipt = ReceiptRecord(
        uploaded_by_user_id=uploaded_by_user_id,
        file_path=file_path,
        file_name=file_name,
        mime_type=mime_type,
        total_amount=total_amount,
        vendor=vendor,
        notes=notes,
        uploaded_via=uploaded_via,
        telegram_request_message_id=telegram_request_message_id,
    )
    db.add(receipt)
    await db.flush()
    await db.refresh(receipt)
    log.info("Receipt: receipt=%d via=%s", receipt.id, uploaded_via)
    return receipt
