# Codebase Guide

A map of the repository for anyone picking up this project.

---

## Repository Layout

```
cabinet-inventory/
├── backend/                  Python + FastAPI
│   ├── app/
│   │   ├── main.py           App factory, lifespan, scheduler, CORS
│   │   ├── config.py         Settings loaded from .env via pydantic-settings
│   │   ├── database.py       SQLAlchemy async engine + session factory
│   │   ├── dependencies.py   FastAPI deps: get_db, get_current_user
│   │   ├── models/           SQLAlchemy ORM models (one file per table)
│   │   │   ├── cabinet.py
│   │   │   ├── bin.py            includes qr_token field
│   │   │   ├── item.py           includes is_consumable, unit_price
│   │   │   ├── transaction.py    includes photo_request_message_id
│   │   │   ├── transaction_photo.py
│   │   │   ├── bin_transaction.py
│   │   │   ├── usage_event.py    consumable usage events
│   │   │   ├── stock_adjustment.py
│   │   │   ├── inventory_request.py
│   │   │   ├── purchase_record.py
│   │   │   ├── receipt_record.py includes telegram_file_id
│   │   │   ├── role.py
│   │   │   └── user.py
│   │   ├── schemas/          Pydantic request/response schemas
│   │   │   ├── item.py
│   │   │   ├── transaction.py
│   │   │   ├── usage_event.py
│   │   │   ├── stock_adjustment.py
│   │   │   ├── inventory_request.py
│   │   │   ├── purchase.py
│   │   │   └── report.py
│   │   ├── routers/          HTTP route handlers (one file per domain)
│   │   │   ├── auth.py             /api/auth
│   │   │   ├── users.py            /api/users
│   │   │   ├── cabinets.py         /api/cabinets
│   │   │   ├── bins.py             /api/bins
│   │   │   ├── items.py            /api/items
│   │   │   ├── transactions.py     /api/transactions
│   │   │   ├── bin_transactions.py /api/bin-transactions
│   │   │   ├── usage_events.py     /api/usage-events
│   │   │   ├── stock_adjustments.py /api/stock-adjustments
│   │   │   ├── moves.py            /api/moves/item, /api/moves/bin
│   │   │   ├── requests.py         /api/requests
│   │   │   ├── purchases.py        /api/purchases, /api/purchases/receipts
│   │   │   ├── reports.py          /api/reports/inventory-status, /expenses
│   │   │   └── telegram_webhook.py /api/telegram
│   │   ├── services/         Business logic (no HTTP concerns)
│   │   │   ├── auth_service.py
│   │   │   ├── transaction_service.py  checkout_item, return_item, mark_overdue
│   │   │   ├── usage_service.py        log_usage_event
│   │   │   ├── stock_service.py        apply_stock_adjustment
│   │   │   ├── move_service.py         move_item, move_bin (cascades cabinet_id to items)
│   │   │   ├── request_service.py      approve_request (creates real Transaction/BinTransaction)
│   │   │   ├── purchase_service.py     log_purchase, create_receipt
│   │   │   └── telegram_service.py     all Telegram sends
│   │   ├── core/
│   │   │   ├── security.py       hash_password, verify_password, JWT
│   │   │   ├── permissions.py    require_*() guards, 403 raises
│   │   │   └── exceptions.py     NotFoundError, InsufficientStockError,
│   │   │                         TransactionConflictError, PermissionDeniedError
│   │   └── bot/
│   │       └── handlers.py       handle_update, handle_receipt_photo_reply,
│   │                             handle_photo_reply, cmd_* handlers
│   ├── migrations/           Alembic migration scripts
│   │   └── versions/
│   │       ├── 001_initial_schema.py
│   │       ├── 002_add_photo_request_message_id.py
│   │       ├── 003_extend_items_bins_qr.py
│   │       ├── 004_usage_stock_location.py
│   │       ├── 005_bin_transactions.py
│   │       ├── 006_inventory_requests.py
│   │       ├── 007_purchase_receipt.py
│   │       └── 008_receipt_telegram_file_id.py
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   ├── test_inventory.py
│   │   ├── test_permissions.py
│   │   ├── test_transactions.py
│   │   └── test_consumable_usage.py   consumables, bin checkout, stock adj, requests
│   ├── .env.example
│   ├── alembic.ini
│   ├── pytest.ini
│   └── requirements.txt
│
├── frontend/                 React + TypeScript + Vite
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx           Router, RequireAuth, route tree
│   │   ├── index.css         Tailwind base + custom component classes
│   │   ├── types/index.ts    All TypeScript interfaces
│   │   ├── api/
│   │   │   ├── client.ts         Axios instance, auth interceptor, camelCase converter
│   │   │   ├── auth.ts
│   │   │   ├── cabinets.ts
│   │   │   ├── items.ts          createItem accepts isConsumable, unitPrice
│   │   │   ├── transactions.ts
│   │   │   ├── binTransactions.ts
│   │   │   ├── usageEvents.ts
│   │   │   ├── stockAdjustments.ts
│   │   │   ├── moves.ts
│   │   │   ├── requests.ts
│   │   │   ├── purchases.ts
│   │   │   └── reports.ts        getInventoryStatus, getExpenseReport(start, end, itemId?)
│   │   ├── store/
│   │   │   └── auth.ts
│   │   ├── pages/
│   │   │   ├── LoginPage.tsx
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── InventoryListPage.tsx  search, cabinet/bin filter, location column
│   │   │   ├── CabinetDetailPage.tsx  BinSection with checkout/return, QR button
│   │   │   ├── ItemDetailPage.tsx     consumable UI, move, stock adjust, usage history
│   │   │   ├── TransactionsPage.tsx
│   │   │   ├── ReportsPage.tsx        period picker, item filter, purchases/usage tabs
│   │   │   ├── QRScanPage.tsx         role-aware: coordinator gets checkout/return, user gets request form
│   │   │   ├── AdminPage.tsx
│   │   │   └── SettingsPage.tsx       Telegram linking, mobile logout
│   │   └── components/
│   │       ├── layout/
│   │       │   ├── AppShell.tsx
│   │       │   ├── Sidebar.tsx
│   │       │   └── MobileNav.tsx
│   │       ├── modals/
│   │       │   ├── CabinetModal.tsx
│   │       │   ├── BinModal.tsx
│   │       │   ├── BinQRModal.tsx      QR display, PNG/SVG download, print
│   │       │   ├── ItemModal.tsx       includes is_consumable, unit_price fields
│   │       │   ├── UserModal.tsx
│   │       │   ├── MarkAsUsedModal.tsx consumable usage form
│   │       │   ├── StockAdjustModal.tsx manual stock adjustment
│   │       │   └── MoveModal.tsx       move item or bin to different cabinet/bin
│   │       └── transactions/
│   │           ├── CheckoutModal.tsx
│   │           ├── ReturnModal.tsx
│   │           └── TransactionRow.tsx
│   ├── vite.config.ts
│   └── package.json
│
├── docs/
└── .github/workflows/
```

---

## Backend

### Entry point: `app/main.py`

Creates the FastAPI app, registers all routers under `/api`, sets up CORS, and manages startup/shutdown via the `lifespan` context manager. On startup it:
- Starts APScheduler to run `mark_overdue_transactions()` hourly
- Registers the Telegram webhook with Telegram's API (production only)

### Config: `app/config.py`

A single `Settings` class (pydantic-settings) reads all config from environment variables / `.env`. Access anywhere via `from app.config import settings`. Key fields: `database_url`, `secret_key`, `telegram_bot_token`, `telegram_coordinator_chat_id`.

### Database: `app/database.py`

Sets up the async SQLAlchemy engine (`asyncpg` driver) and `AsyncSessionLocal` session factory. All DB access is async. Tests swap this out for an in-memory SQLite engine.

### Dependencies: `app/dependencies.py`

Two FastAPI dependencies used across all routers:
- `get_db` — yields an `AsyncSession`
- `get_current_user` — validates the JWT, returns the `User` ORM object with role loaded

### Models (`app/models/`)

One file per database table. SQLAlchemy 2.0 `Mapped`/`mapped_column` style.

`Item.quantity_available` is a **denormalized cache**. It is updated atomically (with `SELECT FOR UPDATE`) during checkout, return, usage events, and stock adjustments. Never update it directly.

### Schemas (`app/schemas/`)

Pydantic models for request bodies (`*Create`, `*Update`) and response shapes (`*Out`). The API returns snake_case. The frontend axios client converts to camelCase automatically.

### Routers (`app/routers/`)

Thin HTTP handlers per domain. Routers call services; they don't contain complex business logic or raw SQL (except simple list queries).

### Services (`app/services/`)

| File | Purpose |
|---|---|
| `auth_service.py` | `authenticate_user()` |
| `transaction_service.py` | `checkout_item()`, `return_item()`, `cancel_transaction()`, `mark_overdue_transactions()` — raises `TransactionConflictError` for consumables or bin items |
| `usage_service.py` | `log_usage_event()` — raises `TransactionConflictError` (409) for non-consumables |
| `stock_service.py` | `apply_stock_adjustment()` — raises `TransactionConflictError` (409) for invalid deltas |
| `move_service.py` | `move_item()`, `move_bin()` — bin move cascades `cabinet_id` to all items in the bin |
| `request_service.py` | `approve_request()` — creates real `Transaction`/`BinTransaction`, sets status to FULFILLED; `deny_request()` |
| `purchase_service.py` | `log_purchase()`, `create_receipt()` |
| `telegram_service.py` | `notify_checkout()`, `notify_return_and_request_photo()`, `notify_overdue()`, `notify_purchase_and_request_receipt()` (sends group + DM), `notify_new_request()`, `notify_account_linked()` |

`transaction_service` is the most critical file. All quantity mutations use row-level locking (`SELECT FOR UPDATE`).

### Core (`app/core/`)

| File | Purpose |
|---|---|
| `security.py` | `hash_password()`, `verify_password()`, `create_access_token()`, `decode_token()` |
| `permissions.py` | `require_*()` guard functions that raise 403 |
| `exceptions.py` | `NotFoundError`, `InsufficientStockError`, `TransactionConflictError`, `PermissionDeniedError` |

### Bot (`app/bot/handlers.py`)

`handle_update()` dispatches to command handlers or photo-reply handlers:

- **Photo replies** → tried in order: `handle_receipt_photo_reply()` (matches `ReceiptRecord.telegram_request_message_id`), then `handle_photo_reply()` (matches `Transaction.photo_request_message_id`)
- **Commands**: `/start`, `/link`, `/myitems`, `/overdue`, `/status`, `/requests`, `/approve`, `/deny`

### Migrations (`migrations/versions/`)

Run with `alembic upgrade head`. Migrations in sequence:
- `001` — full initial schema + role seed data
- `002` — `photo_request_message_id` on transactions
- `003` — `is_consumable`, `unit_price`, `qr_token` on items/bins
- `004` — usage events, stock adjustments, location tracking
- `005` — bin transactions
- `006` — inventory requests
- `007` — purchase records and receipt records
- `008` — `telegram_file_id` on receipt records

### Tests (`tests/`)

SQLite in-memory DB (fast, no external dependency). The `conftest.py` fixture drops and recreates all tables before each test. HTTP tests use httpx's `ASGITransport`.

Run with: `.venv/bin/python -m pytest tests/` from the `backend/` directory.

---

## Frontend

### Data fetching

All API calls go through `src/api/client.ts` — an axios instance with:
1. **Request interceptor**: attaches `Authorization: Bearer <token>` from localStorage
2. **Response interceptor**: deep-converts snake_case keys to camelCase (`camelcase-keys`), redirects to `/login` on 401

TanStack Query wraps every API call. After mutations, the relevant query keys are invalidated to trigger a refetch.

### Auth state

`src/store/auth.ts` is a Zustand store holding the `user` object (with nested `role`). `hydrate()` is called once on app mount — reads the token from localStorage and calls `/api/auth/me`. Until hydration completes, `RequireAuth` shows a spinner.

### Routing

`src/App.tsx` defines the route tree. All authenticated routes are wrapped in `RequireAuth`. The `AppShell` layout wraps all inner routes.

### CSS conventions

`src/index.css` defines reusable component classes:

| Class | Used for |
|---|---|
| `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger` | Buttons |
| `.card` | White rounded-xl panel with shadow |
| `.input` | Form inputs and selects |
| `.label` | Form field labels |
| `.badge`, `.badge-green`, `.badge-yellow`, `.badge-red`, `.badge-slate`, `.badge-blue` | Status chips |

### TypeScript types

All shared types live in `src/types/index.ts` in camelCase. If the backend adds a new field, add it here too.

---

## Key Design Decisions

**Why is `quantity_available` on Item if Transaction is the source of truth?**
Fast availability checks without aggregating transactions. The tradeoff is that `quantity_available` must always be updated atomically alongside the Transaction, which is why all quantity changes go through `transaction_service` with row locks.

**Why can't consumables be checked out?**
Consumables are physically consumed — there is nothing to return. Using a `UsageEvent` instead of a `Transaction` makes the intent explicit and produces clean consumption history for expense reporting.

**Why can't bin items be individually checked out?**
Bins are managed as units. Individual checkout of bin items would create ambiguous state (the item is "checked out" but the bin is still in the cabinet). The `BinTransaction` model enforces atomic checkout of all bin contents.

**Why does request approval create real Transactions?**
A request approval must actually move inventory — decrement stock and create an audit record. A status-only toggle would leave the inventory inconsistent.

**Why does `move_bin` cascade `cabinet_id` to items?**
Items store their `cabinet_id` for fast filtering without a JOIN through Bin. When a bin moves, all its items must update to reflect the new location.

**Why Telegram for photos instead of file upload?**
Simplifies backend storage (no S3/Cloudinary, no file size limits, no CDN). Telegram stores photos indefinitely; the `file_id` is stable. Tradeoff: photos aren't visible in the web UI.

**Why SQLite for tests?**
Speed. In-memory SQLite means no Docker dependency in CI, each test starts with a clean schema in milliseconds. Tradeoff: SQLite dialect differences (no `FOR UPDATE`, no timezone-aware datetimes).
