# Architecture

## Overview

Cabinet Inventory is a monorepo containing a FastAPI backend, a React frontend, and a Telegram bot integrated into the backend process. All components run from a single GitHub repository.

```
┌─────────────────┐     HTTPS/REST      ┌───────────────────────────────┐
│  React Frontend │ ◄──────────────────► │     FastAPI Backend (Render)   │
│    (Vercel)     │                      │                               │
└─────────────────┘                      │  ┌────────────┐              │
                                         │  │ Routers    │              │
┌─────────────────┐     Webhook POST     │  │ Services   │              │
│  Telegram Bot   │ ─────────────────►  │  │ Models     │              │
│   (Telegram     │                      │  └─────┬──────┘              │
│    servers)     │                      │        │ async SQLAlchemy    │
└─────────────────┘                      └────────┼──────────────────────┘
                                                  │
                                         ┌────────▼──────────┐
                                         │  PostgreSQL        │
                                         │  (Neon.tech free)  │
                                         └───────────────────┘
```

## Components

### FastAPI Backend

- **Routers**: HTTP endpoints for auth, cabinets, bins, items, transactions, users, Telegram webhook
- **Services**: Business logic layer (transaction_service, telegram_service, inventory_service, auth_service)
- **Models**: SQLAlchemy ORM entities
- **Schemas**: Pydantic request/response models
- **Core**: Security utilities (JWT, bcrypt), permission helpers, exception types
- **Bot**: Telegram update handlers (called by the webhook router)
- **Scheduler**: APScheduler runs `mark_overdue_transactions` hourly inside the FastAPI process

### React Frontend

- Single-page application built with Vite
- TanStack Query polls every 30 seconds for updated data — no WebSockets needed
- Zustand manages auth state (JWT stored in localStorage)
- Protected routes redirect unauthenticated users to /login

### Telegram Bot

- Webhook mode: Telegram POSTs updates to `/api/telegram/webhook/{secret}`
- Bot runs inside the FastAPI process — no separate worker
- Notifications fire after commits (checkout, return, overdue)
- Account linking via one-time token generated in the web app

## Request Flow: Checkout

1. User clicks "Check out" in the React UI
2. POST `/api/transactions/checkout` with item_id, user_id, quantity, due_at
3. `transactions` router calls `transaction_service.checkout_item()`
4. Service locks the Item row, checks quantity, decrements `quantity_available`, creates Transaction
5. DB commit
6. `telegram_service.notify_checkout()` fires (async, non-blocking)
7. 201 response with Transaction JSON
8. TanStack Query invalidates `["items"]` and `["transactions"]` caches on success

## Request Flow: Return

1. User clicks "Return" in the UI (TransactionRow or ReturnModal)
2. POST `/api/transactions/{id}/return`
3. Service locks Transaction and Item rows, marks RETURNED, increments `quantity_available`, sets `photo_requested_via_telegram=True`
4. DB commit
5. `telegram_service.notify_return_and_request_photo()` fires — bot posts in coordinator channel asking for a condition photo
6. 200 response

## Overdue Detection

APScheduler runs `mark_overdue_transactions()` every hour:
1. Finds CHECKED_OUT transactions where `due_at < now()`
2. Updates status to OVERDUE in bulk
3. Sends Telegram DMs to affected users and posts to coordinator channel

## Data Flow Notes

- `Item.quantity_available` is a denormalized cache. It is updated atomically (with row-level locking) during checkout and return.
- Transaction is the authoritative audit record. `Item.quantity_available` can be recomputed via: `SELECT quantity_total - SUM(t.quantity) FROM items JOIN transactions t WHERE t.status IN ('CHECKED_OUT','OVERDUE')`.
- This is intentional: fast reads from Item for availability; full history from Transaction.
