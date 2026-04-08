"""
Telegram webhook endpoint. Telegram POSTs updates here.
The URL includes a secret token to prevent unauthorized calls.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook/{secret}")
async def telegram_webhook(
    secret: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    if secret != settings.telegram_webhook_secret:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid webhook secret")

    from app.bot.handlers import handle_update

    body = await request.json()
    await handle_update(body, db)
    return {"ok": True}
