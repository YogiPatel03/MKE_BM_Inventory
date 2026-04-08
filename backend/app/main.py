import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import sentry_sdk
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import AsyncSessionLocal
from app.routers import auth, bins, cabinets, items, telegram_webhook, transactions, users

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

# Sentry — no-op if DSN is empty
if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment, traces_sample_rate=0.1)

scheduler = AsyncIOScheduler()


async def _run_overdue_check() -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.transaction import Transaction, TransactionStatus
    from app.services.telegram_service import notify_overdue
    from app.services.transaction_service import mark_overdue_transactions

    async with AsyncSessionLocal() as db:
        count = await mark_overdue_transactions(db)
        await db.commit()

        if count > 0:
            result = await db.execute(
                select(Transaction)
                .where(Transaction.status == TransactionStatus.OVERDUE)
                .options(selectinload(Transaction.item), selectinload(Transaction.user))
                .limit(50)
            )
            for t in result.scalars().all():
                await notify_overdue(t)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    scheduler.add_job(_run_overdue_check, "interval", hours=1, id="overdue_check")
    scheduler.start()
    log.info("Startup complete. Scheduler running.")

    if settings.is_production and settings.telegram_enabled:
        from telegram import Bot
        bot = Bot(token=settings.telegram_bot_token)
        webhook_url = (
            f"{settings.backend_url}/api/telegram/webhook/{settings.telegram_webhook_secret}"
        )
        await bot.set_webhook(url=webhook_url)
        log.info("Telegram webhook registered: %s", webhook_url)

    yield

    # Shutdown
    scheduler.shutdown()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(cabinets.router, prefix="/api")
app.include_router(bins.router, prefix="/api")
app.include_router(items.router, prefix="/api")
app.include_router(transactions.router, prefix="/api")
app.include_router(telegram_webhook.router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
