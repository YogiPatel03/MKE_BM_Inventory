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
│   │   ├── schemas/          Pydantic request/response schemas
│   │   ├── routers/          HTTP route handlers (one file per domain)
│   │   ├── services/         Business logic (no HTTP concerns)
│   │   ├── core/             Security, permissions, exceptions
│   │   └── bot/              Telegram update handlers
│   ├── migrations/           Alembic migration scripts
│   │   └── versions/
│   │       ├── 001_initial_schema.py   All tables + role seed data
│   │       └── 002_add_photo_request_message_id.py
│   ├── tests/
│   │   ├── conftest.py       SQLite in-memory test DB, fixtures
│   │   ├── test_auth.py      Login and /me endpoint tests
│   │   ├── test_inventory.py Cabinet / bin / item CRUD tests
│   │   ├── test_permissions.py  RBAC enforcement tests
│   │   └── test_transactions.py Checkout / return / cancel tests
│   ├── .env                  Local secrets (not committed)
│   ├── .env.example          Template for .env
│   ├── alembic.ini
│   ├── pytest.ini
│   └── requirements.txt
│
├── frontend/                 React + TypeScript + Vite
│   ├── src/
│   │   ├── main.tsx          React entry point, QueryClient setup
│   │   ├── App.tsx           Router, RequireAuth guard, route tree
│   │   ├── index.css         Tailwind base + custom component classes
│   │   ├── types/index.ts    All TypeScript interfaces
│   │   ├── api/              Axios wrappers per domain
│   │   │   ├── client.ts     Axios instance, auth interceptor, camelCase converter
│   │   │   ├── auth.ts       login, getMe, createUser, updateUser
│   │   │   ├── cabinets.ts   listCabinets, getCabinet, createCabinet, createBin, listBins, listItems
│   │   │   ├── items.ts      getItem, createItem, updateItem
│   │   │   └── transactions.ts  listTransactions, checkout, returnItem, cancelTransaction
│   │   ├── store/
│   │   │   └── auth.ts       Zustand store: user, login(), logout(), hydrate()
│   │   ├── pages/            Full-page route components
│   │   │   ├── LoginPage.tsx
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── InventoryPage.tsx
│   │   │   ├── CabinetDetailPage.tsx
│   │   │   ├── ItemDetailPage.tsx
│   │   │   ├── TransactionsPage.tsx
│   │   │   ├── AdminPage.tsx
│   │   │   └── SettingsPage.tsx
│   │   └── components/
│   │       ├── layout/
│   │       │   ├── AppShell.tsx    Sidebar + main content + mobile nav wrapper
│   │       │   ├── Sidebar.tsx     Desktop left nav with user info + logout
│   │       │   └── MobileNav.tsx   Fixed bottom tab bar for mobile
│   │       ├── modals/
│   │       │   ├── CabinetModal.tsx   Create cabinet form
│   │       │   ├── BinModal.tsx       Create bin form
│   │       │   ├── ItemModal.tsx      Create item form
│   │       │   └── UserModal.tsx      Create / edit user form
│   │       └── transactions/
│   │           ├── CheckoutModal.tsx  Checkout form (quantity, due date, notes)
│   │           ├── ReturnModal.tsx    Return form (notes)
│   │           └── TransactionRow.tsx Single transaction with Return button
│   ├── vite.config.ts        Vite config — proxies /api to localhost:8000 in dev
│   └── package.json
│
├── docs/                     Project documentation
│   ├── user-manual.md        End-user guide (this project)
│   ├── codebase-guide.md     This file
│   ├── architecture.md       System diagram and request flows
│   ├── domain-model.md       Full entity reference with field tables
│   ├── roles-permissions.md  RBAC definitions and implementation notes
│   ├── telegram-bot.md       Bot commands and notification flows
│   ├── photo-proof-flow.md   How condition photos flow through the system
│   ├── local-dev.md          Setup instructions
│   ├── deployment.md         Render + Vercel + Neon deployment guide
│   └── cost-notes.md         Why this costs $0/month
│
└── .github/workflows/        CI/CD
    ├── backend-ci.yml         pytest on every push
    ├── frontend-ci.yml        tsc + vite build on every push
    └── deploy.yml             Deploy to Render + Vercel on main push
```

---

## Backend

### Entry point: `app/main.py`

Creates the FastAPI app, registers all routers under `/api`, sets up CORS, and manages startup/shutdown via the `lifespan` context manager. On startup it:
- Starts APScheduler to run `mark_overdue_transactions()` hourly
- Registers the Telegram webhook with Telegram's API (production only)

### Config: `app/config.py`

A single `Settings` class (pydantic-settings) reads all config from environment variables / `.env`. Access it anywhere via `from app.config import settings`. Key fields: `database_url`, `secret_key`, `telegram_bot_token`, `telegram_coordinator_chat_id`.

### Database: `app/database.py`

Sets up the async SQLAlchemy engine (`asyncpg` driver) and `AsyncSessionLocal` session factory. All DB access is async. Tests swap this out for an in-memory SQLite engine.

### Dependencies: `app/dependencies.py`

Two FastAPI dependencies used across all routers:
- `get_db` — yields an `AsyncSession`, handles commit/rollback lifecycle
- `get_current_user` — validates the JWT from the `Authorization` header, returns the `User` ORM object with role loaded

### Models (`app/models/`)

One file per database table. All use SQLAlchemy 2.0 `Mapped`/`mapped_column` style. Key relationships:

- `Role` → `User` (many users per role)
- `Cabinet` → `Bin`, `Item`
- `Item` → `Transaction`
- `Transaction` → `TransactionPhoto`
- `User` appears twice on `Transaction`: as `user` (borrower) and `processed_by` (staff)

`Item.quantity_available` is a **denormalized cache**. It is updated atomically (with `SELECT FOR UPDATE`) during checkout and return. Do not update it directly — always go through `transaction_service`.

### Schemas (`app/schemas/`)

Pydantic models for request bodies (`*Create`, `*Update`) and response shapes (`*Out`). FastAPI serializes ORM objects using `model_config = ConfigDict(from_attributes=True)`.

The API returns snake_case JSON. The frontend axios client converts it to camelCase automatically (see `api/client.ts`).

### Routers (`app/routers/`)

Thin HTTP handlers. Each file corresponds to a domain:

| File | Prefix | What it handles |
|---|---|---|
| `auth.py` | `/api/auth` | Login, `/me` |
| `users.py` | `/api/users` | CRUD users, Telegram link token |
| `cabinets.py` | `/api/cabinets` | CRUD cabinets |
| `bins.py` | `/api/bins` | CRUD bins |
| `items.py` | `/api/items` | CRUD items |
| `transactions.py` | `/api/transactions` | List, checkout, return, cancel, get detail |
| `telegram_webhook.py` | `/api/telegram` | Receives updates from Telegram |

Routers call services for business logic. They don't contain SQL directly (except simple list queries).

### Services (`app/services/`)

| File | Purpose |
|---|---|
| `auth_service.py` | `authenticate_user()` — validates credentials, timing-safe |
| `transaction_service.py` | `checkout_item()`, `return_item()`, `cancel_transaction()`, `mark_overdue_transactions()` |
| `telegram_service.py` | All Telegram sends: checkout notification, return + photo request, overdue DM |
| `inventory_service.py` | `get_cabinet_detail()` — cabinet with bin/item counts |

`transaction_service` is the most critical file. All quantity mutations go through it with row-level locking (`SELECT FOR UPDATE`) to prevent race conditions.

### Core (`app/core/`)

| File | Purpose |
|---|---|
| `security.py` | `hash_password()`, `verify_password()`, `create_access_token()`, `decode_token()` |
| `permissions.py` | `require_*()` guard functions that raise 403, plus `can_process_transaction_for()` |
| `exceptions.py` | `NotFoundError`, `InsufficientStockError`, `TransactionConflictError`, `PermissionDeniedError` |

### Bot (`app/bot/handlers.py`)

`handle_update()` is called by the webhook router for every Telegram update. It dispatches to command handlers (`cmd_start`, `cmd_link`, `cmd_my_items`, `cmd_overdue`, `cmd_item_status`) or to `handle_photo_reply()` if the message contains a photo that is a reply to the bot's return notification.

The photo-reply flow: when a return is processed, the bot posts a photo-request message in the coordinator channel and saves the Telegram `message_id` on the transaction. When someone replies to that message with a photo, `handle_photo_reply()` matches the reply's `reply_to_message.message_id` to find the transaction and creates a `TransactionPhoto` record.

### Migrations (`migrations/versions/`)

Run with `alembic upgrade head`. Two migrations exist:
- `001` — full initial schema + seeds 4 roles with correct permission flags
- `002` — adds `photo_request_message_id` to `transactions`

To create a new migration: `alembic revision --autogenerate -m "description"`. Always review the generated file before applying — autogenerate sometimes misses things (e.g. custom constraints, server defaults).

### Tests (`tests/`)

Tests use an in-memory SQLite database (fast, no external dependency). The `conftest.py` fixture drops and recreates all tables before each test. HTTP tests use httpx's `ASGITransport` to call the app directly without a running server.

Run with: `pytest tests/` from the `backend/` directory.

---

## Frontend

### Data fetching

All API calls go through `src/api/client.ts`, which is an axios instance with two interceptors:
1. **Request**: attaches `Authorization: Bearer <token>` from localStorage
2. **Response**: deep-converts snake_case keys to camelCase (using `camelcase-keys`), redirects to `/login` on 401

TanStack Query wraps every API call. Cache keys follow the pattern `["resource", filter]` (e.g. `["transactions", "CHECKED_OUT"]`). After mutations (checkout, return, create), the relevant query keys are invalidated to trigger a refetch.

### Auth state

`src/store/auth.ts` is a Zustand store. It holds the `user` object (with nested `role`) and exposes `login()`, `logout()`, and `hydrate()`. `hydrate()` is called once on app mount — it reads the token from localStorage and calls `/api/auth/me` to restore the session. Until hydration completes, `isLoading` is true and `RequireAuth` shows a spinner.

### Routing

`src/App.tsx` defines the route tree. All authenticated routes are wrapped in `RequireAuth`, which redirects to `/login` if `user` is null. The `AppShell` layout wraps all inner routes and renders the `Sidebar` + `MobileNav`.

### CSS conventions

`src/index.css` defines reusable component classes using Tailwind's `@apply`:

| Class | Used for |
|---|---|
| `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger` | Buttons |
| `.card` | White rounded-xl panel with shadow |
| `.input` | Form inputs and selects |
| `.label` | Form field labels |
| `.badge`, `.badge-green`, `.badge-yellow`, `.badge-red`, `.badge-slate`, `.badge-blue` | Status chips |

Tailwind brand color is configured as `brand` (mapped to indigo) in `tailwind.config.js`.

### TypeScript types

All shared types live in `src/types/index.ts`. These mirror the backend schemas but in camelCase. If the backend adds a new field, add it here too.

---

## Key Design Decisions

**Why is `quantity_available` on Item if Transaction is the source of truth?**
Fast availability checks without aggregating transactions. The tradeoff is that `quantity_available` must always be updated atomically alongside the Transaction, which is why all quantity changes go through `transaction_service` with row locks.

**Why no WebSockets?**
TanStack Query polls every 30 seconds. For a 15-person internal tool, this is sufficient and removes operational complexity. If real-time is needed, add a `refetchInterval` override or drop in a WebSocket later.

**Why Telegram for photos instead of file upload?**
Simplifies backend storage (no S3/Cloudinary needed, no file size limits to manage, no CDN). Telegram stores photos indefinitely and the `file_id` is stable. The tradeoff is that photos aren't visible in the web UI — they live in the coordinator Telegram channel.

**Why admin-only user creation?**
This is an internal inventory system for a known set of people. Open registration would be a security risk. Admins create accounts and hand out credentials directly.

**Why SQLite for tests?**
Speed. In-memory SQLite means no Docker dependency in CI, each test starts with a clean schema in milliseconds, and tests can run in parallel. The tradeoff is SQLite dialect differences (no `FOR UPDATE`, no timezone-aware datetimes) — service-layer tests that need locking run against real PostgreSQL if needed.
