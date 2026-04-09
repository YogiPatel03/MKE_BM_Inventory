from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user as get_current_active_user, get_db
from app.core.permissions import require_process_any_transaction
from app.models.bin_transaction import BinTransaction
from app.models.user import User
from app.schemas.bin_transaction import BinTransactionCreate, BinTransactionOut, BinTransactionReturn
from app.services.bin_transaction_service import checkout_bin, return_bin

router = APIRouter(prefix="/bin-transactions", tags=["bin-transactions"])


@router.post("", response_model=BinTransactionOut, status_code=201)
async def checkout_bin_endpoint(
    body: BinTransactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_process_any_transaction(current_user)
    bin_txn = await checkout_bin(
        db,
        bin_id=body.bin_id,
        user_id=current_user.id,
        processed_by_user_id=current_user.id,
        due_at=body.due_at,
        notes=body.notes,
    )
    await db.commit()
    await db.refresh(bin_txn)
    return bin_txn


@router.post("/{bin_transaction_id}/return", response_model=BinTransactionOut)
async def return_bin_endpoint(
    bin_transaction_id: int,
    body: BinTransactionReturn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_process_any_transaction(current_user)
    bin_txn = await return_bin(
        db,
        bin_transaction_id=bin_transaction_id,
        processed_by_user_id=current_user.id,
        notes=body.notes,
    )
    await db.commit()
    await db.refresh(bin_txn)
    return bin_txn


@router.get("", response_model=List[BinTransactionOut])
async def list_bin_transactions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_process_any_transaction(current_user)
    result = await db.execute(
        select(BinTransaction).order_by(BinTransaction.checked_out_at.desc()).limit(200)
    )
    return result.scalars().all()
