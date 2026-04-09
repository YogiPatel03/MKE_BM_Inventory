# Domain Model

## Entity Relationships

```
Role (1) ────────────── (*) User
Cabinet (1) ─────────── (*) Bin
Cabinet (1) ─────────── (*) Item         [items directly in cabinet]
Bin (1) ─────────────── (*) Item         [items in a bin; bin_id nullable]
Item (1) ────────────── (*) Transaction
Item (1) ────────────── (*) UsageEvent   [consumable consumption log]
Item (1) ────────────── (*) StockAdjustment
Item (1) ────────────── (*) PurchaseRecord
Bin (1) ─────────────── (*) BinTransaction
BinTransaction (1) ───── (*) Transaction [child transactions for bin items]
User (1) ────────────── (*) Transaction  [as borrower]
User (1) ────────────── (*) Transaction  [as processed_by]
Transaction (1) ─────── (*) TransactionPhoto
ReceiptRecord (1) ────── (*) PurchaseRecord
User (1) ────────────── (*) InventoryRequest [as requester]
Item (1) ────────────── (*) InventoryRequest
Bin (1) ─────────────── (*) InventoryRequest
```

## Role

Defines the permission set for a class of users. Seeded in migration 001.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| name | str unique | ADMIN, COORDINATOR, GROUP_LEAD, USER |
| can_manage_inventory | bool | Create/edit/deactivate items, log purchases |
| can_manage_cabinets | bool | Create/edit/delete cabinets |
| can_manage_bins | bool | Create/edit/delete bins |
| can_manage_users | bool | Create/edit users, assign roles |
| can_process_any_transaction | bool | Checkout/return on behalf of any user |
| can_view_all_transactions | bool | See all transactions, not just own |
| can_view_audit_logs | bool | Full audit log access |
| can_approve_requests | bool | Approve/deny inventory requests |

**Built-in role permissions:**

| Role | Inv | Cab | Bin | Users | Process any | View all | Audit | Approve |
|---|---|---|---|---|---|---|---|---|
| ADMIN | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| COORDINATOR | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ |
| GROUP_LEAD | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ✗ |
| USER | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

## User

System account. Created only by ADMIN users. No self-registration.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| full_name | str | Display name |
| username | str unique | Lowercase, used for login |
| password_hash | str | bcrypt |
| telegram_handle | str nullable | e.g. "alice" (no @) |
| telegram_chat_id | str nullable | Set when user runs /link in bot |
| telegram_link_token | str nullable | One-time token, cleared after use |
| role_id | FK → roles | |
| is_active | bool | Soft deactivation |
| created_at, updated_at | datetime tz | |

## Cabinet

Top-level physical storage unit.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| name | str | e.g. "Electronics Cabinet A" |
| location | str nullable | e.g. "Room 204, shelf 3" |
| description | str nullable | |
| created_at, updated_at | datetime tz | |

**Children:** bins (cascade delete), items (direct)

## Bin

Sub-container inside a cabinet. Can be checked out as a unit.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| cabinet_id | FK → cabinets | CASCADE delete |
| label | str | e.g. "Bin A1" |
| group_number | int nullable | Optional grouping within cabinet |
| location_note | str nullable | e.g. "Top shelf, left" |
| description | str nullable | |
| qr_token | str nullable unique | Used in QR scan URL `/qr/bin/{id}` |
| created_at, updated_at | datetime tz | |

**Bin checkout rule:** items inside a bin cannot be individually checked out — the bin must be checked out as a whole via `BinTransaction`.

## Item

A trackable inventory object. Lives in a cabinet, optionally inside a bin.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| name | str | |
| description | str nullable | |
| quantity_total | int ≥ 0 | Total units in inventory |
| quantity_available | int ≥ 0 | Denormalized cache — updated on checkout/return/usage |
| cabinet_id | FK → cabinets | |
| bin_id | FK → bins nullable | null = item is directly in cabinet |
| sku | str nullable unique | External product code |
| condition | str | GOOD, FAIR, POOR, DAMAGED |
| is_consumable | bool | If true, items are used up (not returned) |
| unit_price | Numeric(10,2) nullable | Cost per unit; used for expense reporting |
| is_active | bool | Soft delete |
| created_at, updated_at | datetime tz | |

**Important:** `quantity_available` is a cached value updated atomically. For consumables, both `quantity_total` and `quantity_available` are reduced permanently on usage. Non-consumables use checkout/return flow.

**Checkout rules:**
- Consumable items → cannot be checked out; use `POST /usage-events` instead
- Bin items → cannot be individually checked out; use `POST /bin-transactions/checkout`

## Transaction

The authoritative checkout/return record for **non-consumable** items.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| item_id | FK → items | |
| user_id | FK → users | The person borrowing the item |
| processed_by_user_id | FK → users nullable | Staff member who processed it |
| bin_transaction_id | FK → bin_transactions nullable | Set when part of a bin checkout |
| quantity | int > 0 | Units involved |
| status | str | CHECKED_OUT, RETURNED, OVERDUE, CANCELLED |
| checked_out_at | datetime tz | Auto-set to now() |
| due_at | datetime tz nullable | |
| returned_at | datetime tz nullable | Set on return |
| notes | str nullable | |
| photo_requested_via_telegram | bool | True after bot sends photo request |
| photo_request_message_id | str nullable | Coordinator channel message_id |
| created_at, updated_at | datetime tz | |

**Status transitions:**
```
CHECKED_OUT → RETURNED   (via return endpoint)
CHECKED_OUT → OVERDUE    (via scheduler)
CHECKED_OUT → CANCELLED  (coordinator only)
OVERDUE     → RETURNED
OVERDUE     → CANCELLED
```

## BinTransaction

Checkout/return of an entire bin as one unit.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| bin_id | FK → bins | |
| checked_out_by_user_id | FK → users | |
| processed_by_user_id | FK → users nullable | |
| status | str | CHECKED_OUT, RETURNED |
| notes | str nullable | |
| checked_out_at | datetime tz | |
| returned_at | datetime tz nullable | |
| created_at | datetime tz | |

A `BinTransaction` creates one child `Transaction` per active item in the bin at checkout time, with `bin_transaction_id` set on each.

## TransactionPhoto

Proof photo for a return. Stored as a Telegram reference.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| transaction_id | FK → transactions CASCADE | |
| uploaded_by_user_id | FK → users nullable | |
| telegram_message_id | str nullable | |
| telegram_file_id | str nullable | |
| telegram_chat_id | str nullable | |
| caption | str nullable | |
| uploaded_at | datetime tz | |

## UsageEvent

Permanent stock reduction for consumable items.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| item_id | FK → items | Must be `is_consumable = True` |
| used_by_user_id | FK → users | |
| quantity_used | int > 0 | |
| notes | str nullable | |
| used_at | datetime tz | Auto-set to now() |
| created_at | datetime tz | |

Raises `TransactionConflictError` (409) if `item.is_consumable` is False.

## StockAdjustment

Manual inventory correction record.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| item_id | FK → items | |
| adjusted_by_user_id | FK → users | |
| delta | int | Positive (add) or negative (remove) |
| reason | str | CORRECTION, DAMAGED, LOST, RESTOCK, AUDIT, OTHER |
| notes | str nullable | |
| adjusted_at | datetime tz | Auto-set to now() |
| created_at | datetime tz | |

Raises `TransactionConflictError` (409) if delta would take `quantity_available` below 0.

## InventoryRequest

Request submitted by a USER for an item or bin that they cannot check out themselves.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| requester_id | FK → users | |
| item_id | FK → items nullable | Item being requested |
| bin_id | FK → bins nullable | Bin being requested (mutually exclusive with item_id) |
| quantity_requested | int | |
| reason | str nullable | |
| status | str | PENDING, FULFILLED, DENIED |
| approved_by_user_id | FK → users nullable | Set on approval/denial |
| denial_reason | str nullable | |
| fulfilled_at | datetime tz nullable | Set when status → FULFILLED |
| telegram_request_message_id | str nullable | Coordinator channel message_id |
| created_at | datetime tz | |

**Approval flow:** calling `POST /requests/{id}/approve` checks stock, creates real `Transaction`/`BinTransaction` records, decrements `quantity_available`, and sets `status = FULFILLED`.

## PurchaseRecord

Restocking event: items added to inventory with cost tracking.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| item_id | FK → items | |
| purchased_by_user_id | FK → users | |
| receipt_id | FK → receipt_records nullable | |
| quantity_purchased | int > 0 | |
| unit_price | Numeric(10,2) nullable | Price per unit at time of purchase |
| total_price | Numeric(10,2) nullable | |
| vendor | str nullable | |
| notes | str nullable | |
| purchased_at | datetime tz | |
| created_at | datetime tz | |

## ReceiptRecord

A receipt image associated with a purchase. Can arrive via Telegram or web upload.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| uploaded_by_user_id | FK → users nullable | |
| file_path | str nullable | Server path (web upload) |
| file_name | str nullable | |
| mime_type | str nullable | |
| total_amount | Numeric(10,2) nullable | |
| vendor | str nullable | |
| notes | str nullable | |
| uploaded_via | str | 'web' or 'telegram' |
| telegram_request_message_id | str nullable | Coordinator channel message_id for photo matching |
| telegram_file_id | str nullable | Set when receipt photo received via Telegram |
| uploaded_at, created_at | datetime tz | |

A placeholder `ReceiptRecord` is created immediately when a purchase is logged. Its `telegram_request_message_id` is set from the bot's group notification. When the purchaser replies with a photo, `telegram_file_id` is populated by the bot handler.
