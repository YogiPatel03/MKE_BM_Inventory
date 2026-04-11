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
│   │   │   ├── room.py           NEW — top-level physical location
│   │   │   ├── cabinet.py        includes room_id FK
│   │   │   ├── bin.py            includes qr_token field
│   │   │   ├── item.py           includes is_consumable, unit_price
│   │   │   ├── transaction.py    includes photo_request_message_id
│   │   │   ├── transaction_photo.py
│   │   │   ├── bin_transaction.py
│   │   │   ├── checklist.py      NEW — Checklist, ChecklistItem, ChecklistAssignment, GroupName
│   │   │   ├── usage_event.py    consumable usage events
│   │   │   ├── stock_adjustment.py
│   │   │   ├── inventory_request.py
│   │   │   ├── purchase_record.py
│   │   │   ├── receipt_record.py includes telegram_file_id
│   │   │   ├── activity_log.py
│   │   │   ├── role.py
│   │   │   └── user.py           includes group_name field
│   │   ├── schemas/          Pydantic request/response schemas
│   │   │   ├── room.py           NEW
│   │   │   ├── cabinet.py        includes room_id, bin_count, item_count
│   │   │   ├── checklist.py      NEW
│   │   │   ├── item.py
│   │   │   ├── transaction.py
│   │   │   ├── usage_event.py
│   │   │   ├── stock_adjustment.py
│   │   │   ├── inventory_request.py
│   │   │   ├── purchase.py
│   │   │   ├── user.py           includes group_name
│   │   │   └── report.py         includes HeldValue* schemas
│   │   ├── routers/          HTTP route handlers (one file per domain)
│   │   │   ├── auth.py             /api/auth
│   │   │   ├── users.py            /api/users
│   │   │   ├── rooms.py            NEW /api/rooms
│   │   │   ├── cabinets.py         /api/cabinets (now returns bin_count, item_count)
│   │   │   ├── bins.py             /api/bins
│   │   │   ├── items.py            /api/items
│   │   │   ├── transactions.py     /api/transactions (hooks checklist on checkout/return)
│   │   │   ├── bin_transactions.py /api/bin-transactions (hooks checklist on checkout/return)
│   │   │   ├── checklists.py       NEW /api/checklists
│   │   │   ├── usage_events.py     /api/usage-events
│   │   │   ├── stock_adjustments.py /api/stock-adjustments
│   │   │   ├── moves.py            /api/moves/item, /api/moves/bin
│   │   │   ├── requests.py         /api/requests (DMs requester on approve/deny)
│   │   │   ├── purchases.py        /api/purchases, /api/purchases/receipts
│   │   │   ├── reports.py          /api/reports/* (includes held-value)
│   │   │   └── telegram_webhook.py /api/telegram
│   │   ├── services/         Business logic (no HTTP concerns)
│   │   │   ├── auth_service.py
│   │   │   ├── inventory_service.py    NEW get_cabinets_with_counts() via SQL subqueries
│   │   │   ├── checklist_service.py    NEW weekly checklist generation + return task hooks
│   │   │   ├── transaction_service.py  checkout_item, return_item, mark_overdue
│   │   │   ├── usage_service.py        log_usage_event
│   │   │   ├── stock_service.py        apply_stock_adjustment
│   │   │   ├── move_service.py         move_item, move_bin (cascades cabinet_id to items)
│   │   │   ├── request_service.py      approve_request, deny_request
│   │   │   ├── purchase_service.py     log_purchase, create_receipt
│   │   │   ├── restock_service.py      get_or_create_restock_cabinet (startup)
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
│   │       ├── 008_receipt_telegram_file_id.py
│   │       ├── 009_activity_log_and_low_stock.py
│   │       ├── 010_rooms.py          NEW — rooms table, room_id on cabinets, group_name on users
│   │       └── 011_checklists.py     NEW — checklists, checklist_items, checklist_assignments
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   ├── test_inventory.py
│   │   ├── test_permissions.py
│   │   ├── test_transactions.py
│   │   └── test_consumable_usage.py
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
│   │   │   ├── auth.ts           includes createUser/updateUser with groupName
│   │   │   ├── rooms.ts          NEW listRooms, getRoom, createRoom, updateRoom, deleteRoom
│   │   │   ├── cabinets.ts       listCabinets(roomId?), createCabinet requires roomId
│   │   │   ├── checklists.ts     NEW listChecklists, getChecklist, item/assignment CRUD, backfill
│   │   │   ├── users.ts          NEW listUsers, getUser (extracted from AdminPage)
│   │   │   ├── items.ts
│   │   │   ├── transactions.ts
│   │   │   ├── binTransactions.ts
│   │   │   ├── usageEvents.ts
│   │   │   ├── stockAdjustments.ts
│   │   │   ├── moves.ts
│   │   │   ├── requests.ts
│   │   │   ├── purchases.ts
│   │   │   └── reports.ts        getInventoryStatus, getExpenseReport, getHeldValueReport
│   │   ├── store/
│   │   │   └── auth.ts
│   │   ├── pages/
│   │   │   ├── LoginPage.tsx
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── RoomsPage.tsx         NEW — room list with admin CRUD
│   │   │   ├── RoomDetailPage.tsx    NEW — cabinets within a room; cabinet edit/move
│   │   │   ├── InventoryPage.tsx     redirects to /rooms
│   │   │   ├── InventoryListPage.tsx search, cabinet/bin filter, location column
│   │   │   ├── CabinetDetailPage.tsx bins + items; request button for non-privileged users
│   │   │   ├── ItemDetailPage.tsx    consumable UI, move, stock adjust, usage history, request button
│   │   │   ├── ChecklistPage.tsx     NEW — weekly checklists per group with backfill sync
│   │   │   ├── TransactionsPage.tsx
│   │   │   ├── ReportsPage.tsx       4 tabs: Inventory Status, Purchases, Usage, Held Value
│   │   │   ├── RequestsPage.tsx
│   │   │   ├── QRScanPage.tsx        role-aware: coordinator gets checkout/return, user gets request
│   │   │   ├── AdminPage.tsx         user table includes Group column
│   │   │   └── SettingsPage.tsx      Telegram linking, mobile logout
│   │   └── components/
│   │       ├── layout/
│   │       │   ├── AppShell.tsx      min-h-0 on main (mobile scroll fix)
│   │       │   ├── Sidebar.tsx       includes Rooms, Checklist; Reports for coordinators+
│   │       │   └── MobileNav.tsx     4 primary tabs + More slide-up drawer
│   │       ├── modals/
│   │       │   ├── CabinetModal.tsx  create + edit mode; room selector (enables cabinet moves)
│   │       │   ├── BinModal.tsx
│   │       │   ├── BinQRModal.tsx    QR display, PNG/SVG download, print
│   │       │   ├── ItemModal.tsx     includes is_consumable, unit_price fields
│   │       │   ├── UserModal.tsx     includes group selector dropdown
│   │       │   ├── MarkAsUsedModal.tsx
│   │       │   ├── StockAdjustModal.tsx
│   │       │   └── MoveModal.tsx
│   │       └── transactions/
│   │           ├── CheckoutModal.tsx
│   │           ├── ReturnModal.tsx
│   │           └── TransactionRow.tsx
│   ├── vite.config.ts
│   └── package.json
│
├── docs/
│   ├── architecture.md
│   ├── codebase-guide.md         (this file)
│   ├── domain-model.md           includes Room, Checklist, User.group_name
│   ├── implementation-summary.md full change log for the rooms/checklists sprint
│   ├── roles-permissions.md
│   ├── telegram-bot.md
│   ├── photo-proof-flow.md
│   ├── deployment.md
│   ├── local-dev.md
│   └── cost-notes.md
└── .github/workflows/
```

---

## Backend

### Entry point: `app/main.py`

Creates the FastAPI app, registers all routers under `/api`, sets up CORS, and manages startup/shutdown via the `lifespan` context manager. On startup it:
- Starts APScheduler with two jobs:
  - Hourly: `mark_overdue_transactions()`
  - Monday 06:00: `get_or_create_weekly_checklists()` — pre-generates all 4 group checklists for the week
- Registers the Telegram webhook (production only)
- Calls `get_or_create_restock_cabinet()` to ensure the restock sentinel cabinet exists

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

**Inventory hierarchy:** `Room → Cabinet → Bin → Item`

`Item.quantity_available` is a **denormalized cache**. It is updated atomically (with `SELECT FOR UPDATE`) during checkout, return, usage events, and stock adjustments. Never update it directly.

`User.group_name` determines which group's weekly checklist gets auto-return tasks when that user checks out items or bins. Valid values are defined in `GroupName.ALL`: `SHISHU_MANDAL`, `GROUP_1`, `GROUP_2`, `GROUP_3`.

### Schemas (`app/schemas/`)

Pydantic models for request bodies (`*Create`, `*Update`) and response shapes (`*Out`). The API returns snake_case. The frontend axios client converts to camelCase automatically.

`CabinetOut` includes computed `bin_count` and `item_count` fields — these are injected by `get_cabinets_with_counts()`, not stored in the DB.

### Routers (`app/routers/`)

Thin HTTP handlers per domain. Routers call services; they don't contain complex business logic or raw SQL (except simple list queries).

**Checklist hooks** are wired into `transactions.py` and `bin_transactions.py`:
- After checkout → `add_return_task_for_transaction()` or `add_return_task_for_bin_transaction()`
- After return → `auto_complete_return_task_for_transaction()` or `auto_complete_return_task_for_bin()`

### Services (`app/services/`)

| File | Purpose |
|---|---|
| `auth_service.py` | `authenticate_user()` |
| `inventory_service.py` | `get_cabinets_with_counts()` — uses SQL subqueries to return bin/item counts per cabinet without N+1 queries |
| `checklist_service.py` | `get_or_create_weekly_checklists()`, `get_current_checklist_for_group()`, `add_return_task_for_transaction()`, `add_return_task_for_bin_transaction()`, `auto_complete_return_task_for_transaction()`, `auto_complete_return_task_for_bin()`, `complete_checklist_item()` |
| `transaction_service.py` | `checkout_item()`, `return_item()`, `cancel_transaction()`, `mark_overdue_transactions()` — raises `TransactionConflictError` for consumables or bin items |
| `usage_service.py` | `log_usage_event()` — raises `TransactionConflictError` (409) for non-consumables |
| `stock_service.py` | `apply_stock_adjustment()` — raises `TransactionConflictError` (409) for invalid deltas |
| `move_service.py` | `move_item()`, `move_bin()` — bin move cascades `cabinet_id` to all items in the bin |
| `request_service.py` | `approve_request()` — creates real `Transaction`/`BinTransaction`, sets status to FULFILLED; `deny_request()` |
| `purchase_service.py` | `log_purchase()`, `create_receipt()` |
| `restock_service.py` | `get_or_create_restock_cabinet()` — ensures sentinel cabinet exists on startup |
| `telegram_service.py` | `notify_checkout()`, `notify_return_and_request_photo()`, `notify_overdue()`, `notify_purchase_and_request_receipt()`, `notify_new_request()`, `notify_request_approved()`, `notify_request_denied()`, `notify_checklist_return_proof()`, `notify_account_linked()` |

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
- `009` — activity log and low-stock tracking
- `010` — `rooms` table; `room_id` (NOT NULL) on cabinets; all existing cabinets migrated to "Shishu Mandal"; `group_name` on users
- `011` — `checklists`, `checklist_items`, `checklist_assignments` tables

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

Key routes:
| Path | Page |
|---|---|
| `/dashboard` | DashboardPage |
| `/rooms` | RoomsPage |
| `/rooms/:id` | RoomDetailPage |
| `/inventory/cabinets/:id` | CabinetDetailPage |
| `/inventory/items/:id` | ItemDetailPage |
| `/checklist` | ChecklistPage |
| `/transactions` | TransactionsPage |
| `/requests` | RequestsPage |
| `/reports` | ReportsPage |
| `/admin` | AdminPage |
| `/qr/:token` | QRScanPage |

`/inventory` redirects to `/rooms`.

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

All shared types live in `src/types/index.ts` in camelCase. If the backend adds a new field, add it here too. Key additions: `Room`, `GroupName`, `GROUP_DISPLAY`, `GROUP_NAMES`, `Checklist`, `ChecklistItem`, `ChecklistAssignment`, `ChecklistSummary`, `HeldValueReport`.

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

**Why are checklist return tasks created at checkout time, not on a schedule?**
The checkout event has all the context needed (borrower, item, group). A scheduled job would need to diff active transactions against existing tasks — more complex with the same result. The `POST /checklists/backfill-active-transactions` endpoint exists for one-off recovery if tasks were missed (e.g. user had no group set at checkout time).

**Why does held inventory value use `quantity_total` instead of `quantity_available`?**
Checked-out items still belong to the organisation. Using `quantity_total` ensures the reported asset value doesn't fluctuate with checkouts. Items with `unit_price = NULL` contribute $0.
