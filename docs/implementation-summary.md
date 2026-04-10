# Implementation Summary

This document describes all changes made in the Room, Checklist, and UX improvement sprint.

## Changes Summary

### 1. Cabinet Card Counts Fix

**Problem:** Cabinet cards always showed 0 bins and 0 items even when data existed.

**Root cause:** The list endpoint returned raw `Cabinet` ORM objects. The schema had no `bin_count` / `item_count` fields.

**Fix:**
- Added `bin_count: int = 0` and `item_count: int = 0` to `CabinetOut` schema
- Created `get_cabinets_with_counts()` in `inventory_service.py` using SQL subqueries (no N+1) with `func.coalesce`
- Updated `GET /cabinets` router to call this function and accept optional `room_id` filter

---

### 2. Room Model

**New hierarchy:** Room → Cabinet → Bin / Item

**Backend:**
- New model: `Room` (id, name, description, timestamps)
- `Cabinet.room_id` FK added (NOT NULL)
- Migration 010: creates `rooms` table, inserts "Shishu Mandal", migrates all existing cabinets, adds `group_name` to users
- New router: `GET/POST /rooms`, `GET/PATCH/DELETE /rooms/{id}` (manage requires admin)
- `DELETE /rooms/{id}` blocked if room has cabinets

**Frontend:**
- New page: `RoomsPage` — lists rooms with cabinet count, admin create/edit/delete
- New page: `RoomDetailPage` — shows cabinets in a room, "Add Cabinet" pre-fills room
- `InventoryPage` → redirects to `/rooms`
- `CabinetDetailPage` back-link updated to `/rooms/{roomId}`
- `CabinetModal` now requires room selection (dropdown disabled if room pre-set)
- Sidebar and mobile nav updated to use Rooms as primary navigation

---

### 3. Weekly Checklist

**Backend:**
- New model: `Checklist`, `ChecklistItem`, `ChecklistAssignment` (migration 011)
- Group constants: `SHISHU_MANDAL`, `GROUP_1`, `GROUP_2`, `GROUP_3`
- Unique constraint on `(group_name, week_start)` — one checklist per group per week
- `checklist_service.py`:
  - `get_or_create_weekly_checklists` — ensures all 4 checklists exist for current week
  - `get_current_checklist_for_group` — get/create for a specific group
  - `add_return_task_for_transaction` / `add_return_task_for_bin_transaction` — hooks into checkout
  - `auto_complete_return_task_for_transaction` / `...for_bin` — hooks into return
  - `complete_checklist_item` — manual completion with optional Telegram proof request
- APScheduler job: Monday 06:00 pre-generates all 4 checklists
- Router: `GET/POST /checklists`, `GET /checklists/{id}`, item CRUD, assignment CRUD
- Telegram: `notify_checklist_return_proof` sends proof request to coordinator channel

**Frontend:**
- New page: `ChecklistPage` — group filter, accordion list, inline item management
- Add item modal, complete modal (with Telegram proof option), assign user modal
- Role-aware: admins/coordinators can manage; group leads can add items and assign; all can complete

**User group assignment:**
- `group_name` field added to `User` model and `UserOut`/`UserCreate`/`UserUpdate` schemas
- `AdminPage` now shows Group column
- `UserModal` now includes Group dropdown (no group = auto-return tasks disabled for that user)

---

### 4. Checkout Request Flow

**Backend:**
- `POST /requests` accepts `item_id` or `bin_id`
- `POST /requests/{id}/approve` → creates real Transaction/BinTransaction, DMs requester via Telegram
- `POST /requests/{id}/deny` → DMs requester with denial reason
- `notify_request_approved` and `notify_request_denied` added to `telegram_service.py`

**Frontend:**
- `ItemDetailPage`: non-privileged users see "Request checkout" button for non-consumable items
- `CabinetDetailPage`: non-privileged users see "Request" button on available bins (via `BinSection`)
- `QRScanPage`: items → redirect to item detail; bins → inline "Request bin checkout" for non-privileged users

---

### 5. Mobile Navigation Redesign

**Problem:** Many pages were not accessible on mobile.

**Fix:**
- `MobileNav` completely redesigned: 4 primary bottom tabs (Home, Rooms, Activity, Requests) + "More" slide-up drawer
- "More" drawer contains: All Items, Checklist, Reports (coordinator+), Admin (admin only), Settings, Sign out
- Drawer auto-closes on route change and backdrop click
- `AppShell` `<main>` element has `min-h-0` added — fixes "cabinet view disappears on first mobile load" bug

---

### 6. Reports for Coordinators

**Fix:** Desktop sidebar and mobile "More" drawer now show Reports for `canManageInventory` (coordinators) in addition to admins.

---

### 7. Held Inventory Value Report

**Backend:**
- `GET /reports/held-value` — joins Item + Cabinet + Room
- Value = `unit_price × quantity_total` (checked-out items still count — they're still org property)
- Aggregated by room then cabinet, plus per-item detail
- Returns: `total_value`, `by_room[]`, `by_cabinet[]` (within each room), `items[]`

**Frontend:**
- New "Held Value" tab in `ReportsPage`
- Summary card with total, by-room breakdown table, expandable by-cabinet view, full item table

---

## Migrations Added

| Migration | Description |
|---|---|
| `010_rooms.py` | Creates `rooms` table; adds `room_id` to cabinets (migrates all to "Shishu Mandal"); adds `group_name` to users |
| `011_checklists.py` | Creates `checklists`, `checklist_items`, `checklist_assignments` tables |

---

## Endpoints Added / Changed

### New Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/rooms` | List all rooms |
| POST | `/rooms` | Create room (admin) |
| GET | `/rooms/{id}` | Get room detail |
| PATCH | `/rooms/{id}` | Update room (admin) |
| DELETE | `/rooms/{id}` | Delete room (admin; blocked if has cabinets) |
| GET | `/checklists` | List checklists (filter by group, week) |
| POST | `/checklists` | Create checklist (admin/coordinator) |
| GET | `/checklists/{id}` | Get checklist with items and assignments |
| POST | `/checklists/{id}/items` | Add item to checklist |
| PATCH | `/checklists/{id}/items/{item_id}` | Complete an item |
| DELETE | `/checklists/{id}/items/{item_id}` | Delete an item |
| POST | `/checklists/{id}/assignments` | Assign user to checklist |
| DELETE | `/checklists/{id}/assignments/{assignment_id}` | Unassign user |
| GET | `/reports/held-value` | Held inventory value report |

### Changed Endpoints

| Method | Path | Change |
|---|---|---|
| GET | `/cabinets` | Now accepts `room_id` query param; returns `bin_count` and `item_count` |
| POST | `/cabinets` | Now requires `room_id` in body |
| PATCH | `/cabinets/{id}` | Accepts optional `room_id` to move cabinet |
| POST | `/transactions/checkout` | After checkout: auto-creates return task on group checklist |
| POST | `/transactions/{id}/return` | After return: auto-completes linked return task |
| POST | `/bin-transactions/checkout` | After checkout: auto-creates return task on group checklist |
| POST | `/bin-transactions/{id}/return` | After return: auto-completes linked return task |
| POST | `/requests/{id}/approve` | Now DMs requester via Telegram |
| POST | `/requests/{id}/deny` | Now DMs requester via Telegram |

---

## Frontend Routes / Pages / Components Added or Changed

### New Routes

| Route | Page | Description |
|---|---|---|
| `/rooms` | `RoomsPage` | Room list |
| `/rooms/:id` | `RoomDetailPage` | Cabinets in a room |
| `/checklist` | `ChecklistPage` | Weekly checklists |

### Changed Routes

| Route | Change |
|---|---|
| `/inventory` | Now redirects to `/rooms` |
| `/inventory/cabinets/:id` | Back link goes to `/rooms/{roomId}` |

### New Files

| File | Description |
|---|---|
| `frontend/src/pages/RoomsPage.tsx` | Room list with admin CRUD |
| `frontend/src/pages/RoomDetailPage.tsx` | Cabinets within a room |
| `frontend/src/pages/ChecklistPage.tsx` | Weekly checklists per group |
| `frontend/src/api/rooms.ts` | Room API functions |
| `frontend/src/api/checklists.ts` | Checklist API functions |
| `frontend/src/api/users.ts` | User API functions (extracted from AdminPage) |
| `backend/app/models/room.py` | Room ORM model |
| `backend/app/models/checklist.py` | Checklist/Item/Assignment ORM models |
| `backend/app/schemas/room.py` | Room Pydantic schemas |
| `backend/app/schemas/checklist.py` | Checklist Pydantic schemas |
| `backend/app/services/checklist_service.py` | Checklist business logic |
| `backend/app/routers/rooms.py` | Room router |
| `backend/app/routers/checklists.py` | Checklist router |

### Changed Files

| File | Change |
|---|---|
| `frontend/src/components/layout/MobileNav.tsx` | Full redesign: 4 tabs + "More" drawer |
| `frontend/src/components/layout/Sidebar.tsx` | Added Rooms, Checklist; Reports for coordinators |
| `frontend/src/components/layout/AppShell.tsx` | Added `min-h-0` to fix mobile scroll bug |
| `frontend/src/components/modals/CabinetModal.tsx` | Room selector dropdown (required) |
| `frontend/src/components/modals/UserModal.tsx` | Group selector dropdown |
| `frontend/src/pages/AdminPage.tsx` | Group column in user table |
| `frontend/src/pages/ReportsPage.tsx` | 4 tabs; new Held Value tab |
| `frontend/src/pages/ItemDetailPage.tsx` | Request checkout button for non-privileged users |
| `frontend/src/pages/CabinetDetailPage.tsx` | Request button on bins; updated back-link |
| `frontend/src/pages/InventoryPage.tsx` | Redirects to /rooms |
| `frontend/src/api/cabinets.ts` | `listCabinets(roomId?)`, `createCabinet` requires roomId |
| `frontend/src/api/reports.ts` | `getHeldValueReport()` |
| `frontend/src/api/auth.ts` | `createUser`/`updateUser` accept `groupName` |
| `frontend/src/types/index.ts` | Room, GroupName, Checklist*, HeldValue* interfaces; `groupName` on User |
| `backend/app/models/__init__.py` | Added Room, Checklist, ChecklistItem, ChecklistAssignment |
| `backend/app/models/cabinet.py` | Added `room_id` FK and `room` relationship |
| `backend/app/models/user.py` | Added `group_name` field |
| `backend/app/schemas/cabinet.py` | Added `room_id`, `bin_count`, `item_count` to CabinetOut |
| `backend/app/schemas/report.py` | Added HeldValue* schemas |
| `backend/app/schemas/user.py` | Added `group_name` to UserOut/UserCreate/UserUpdate |
| `backend/app/services/inventory_service.py` | `get_cabinets_with_counts()` |
| `backend/app/routers/cabinets.py` | Uses `get_cabinets_with_counts`; accepts room_id filter |
| `backend/app/routers/reports.py` | Added `/reports/held-value` endpoint |
| `backend/app/routers/transactions.py` | Checklist hooks on checkout/return |
| `backend/app/routers/bin_transactions.py` | Checklist hooks on checkout/return |
| `backend/app/routers/inventory_requests.py` | Telegram DMs on approve/deny |
| `backend/app/services/telegram_service.py` | `notify_request_approved`, `notify_request_denied`, `notify_checklist_return_proof` |
| `backend/app/main.py` | Registered rooms/checklists routers; Monday 06:00 APScheduler job |

---

## Assumptions

1. **Room migration:** All pre-existing cabinets are migrated into "Shishu Mandal". If a different default room is needed, edit migration 010 before running `alembic upgrade head`.
2. **Held value semantics:** `value = unit_price × quantity_total`. Checked-out items count because they are still org property. Items with `unit_price = NULL` contribute $0 to the total.
3. **Group auto-return tasks:** Only created if the checked-out user has `group_name` set. Users without a group silently skip task creation.
4. **Checklist visibility:** All authenticated users can view checklists (to see their own group's tasks). Only admin/coordinator can manage (add manual items, assign members); group leads can also add items and assign.
5. **QR item scans:** Items always redirect to the item detail page (which has the request button). QR only handles bins inline.
6. **Weekly checklist generation:** Monday 06:00 server time. The scheduler also creates checklists on-demand when accessed, so a first-of-week restart won't break anything.

---

## Remaining Risks / TODOs

| Risk / TODO | Priority | Notes |
|---|---|---|
| Tests for cabinet count fix | High | Verify bin_count + item_count aggregation with real DB |
| Tests for room migration | High | Verify migration 010 doesn't break existing cabinets |
| Tests for checklist auto-generation | High | Mock Monday scheduler; verify 4 checklists created |
| Tests for auto-return task creation | High | Checkout → checklist item appears; return → item auto-completed |
| Tests for request approval flow | Medium | Verify Transaction created on approve; Telegram DM called |
| Tests for held-value report | Medium | Unit price × quantity_total math; NULL price → $0 |
| Bin label shown on QR scan page | Low | Currently shows "Bin #ID"; showing bin label would be better |
| Pagination on checklist items | Low | Large checklists may get long without pagination |
| ActivityLog integration | Low | New Room/Checklist events not logged to activity_log yet |
