# Domain Model

## Entity Relationships

```
Role (1) ────────────── (*) User
Cabinet (1) ─────────── (*) Bin
Cabinet (1) ─────────── (*) Item     [items directly in cabinet]
Bin (1) ─────────────── (*) Item     [items in a bin, bin_id is nullable]
Item (1) ────────────── (*) Transaction
User (1) ────────────── (*) Transaction   [as the borrower]
User (1) ────────────── (*) Transaction   [as processed_by, may differ]
Transaction (1) ─────── (*) TransactionPhoto
```

## Role

Defines the permission set for a class of users. Created by seed migration.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| name | str unique | ADMIN, COORDINATOR, GROUP_LEAD, USER |
| can_manage_inventory | bool | Create/edit/deactivate items |
| can_manage_cabinets | bool | Create/edit/delete cabinets |
| can_manage_bins | bool | Create/edit/delete bins |
| can_manage_users | bool | Create/edit users, assign roles |
| can_process_any_transaction | bool | Checkout/return on behalf of any user |
| can_view_all_transactions | bool | See all transactions, not just own |
| can_view_audit_logs | bool | Full audit log access |

**Built-in role permissions:**

| Role | Inv | Cab | Bin | Users | Process any | View all | Audit |
|---|---|---|---|---|---|---|---|
| ADMIN | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| COORDINATOR | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| GROUP_LEAD | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ |
| USER | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

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

Sub-container inside a cabinet.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| cabinet_id | FK → cabinets | CASCADE delete |
| label | str | e.g. "Bin A1" |
| group_number | int nullable | Optional grouping within cabinet |
| location_note | str nullable | e.g. "Top shelf, left" |
| description | str nullable | |
| created_at, updated_at | datetime tz | |

Bins do **not** own checkout state. They are physical location anchors only.

## Item

A trackable inventory object. Lives in a cabinet, optionally inside a bin.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| name | str | |
| description | str nullable | |
| quantity_total | int ≥ 0 | Total units in inventory |
| quantity_available | int ≥ 0 | Denormalized cache — updated on checkout/return |
| cabinet_id | FK → cabinets | |
| bin_id | FK → bins nullable | null = item is directly in cabinet |
| sku | str nullable unique | External product code |
| condition | str | GOOD, FAIR, POOR, DAMAGED |
| is_active | bool | Soft delete |
| created_at, updated_at | datetime tz | |

**Constraints:** `quantity_available >= 0`, `quantity_available <= quantity_total`

**Important:** `quantity_available` is a cached value. `Transaction` is the audit source of truth.

## Transaction

The authoritative checkout/return record. Every item movement is captured here.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| item_id | FK → items | |
| user_id | FK → users | The person borrowing the item |
| processed_by_user_id | FK → users nullable | The staff member who processed it |
| quantity | int > 0 | Units involved in this transaction |
| status | str | CHECKED_OUT, RETURNED, OVERDUE, CANCELLED |
| checked_out_at | datetime tz | Auto-set to now() |
| due_at | datetime tz nullable | Optional due date |
| returned_at | datetime tz nullable | Set on return |
| notes | str nullable | General notes; return notes appended |
| photo_requested_via_telegram | bool | True if bot has requested a proof photo |
| created_at, updated_at | datetime tz | |

**Status transitions:**
```
CHECKED_OUT → RETURNED   (via return endpoint)
CHECKED_OUT → OVERDUE    (via scheduled overdue check)
CHECKED_OUT → CANCELLED  (coordinator only)
OVERDUE     → RETURNED   (via return endpoint — still works)
OVERDUE     → CANCELLED  (coordinator only)
```

## TransactionPhoto

Proof record for a transaction. In v1, photos are provided via Telegram rather than uploaded to the web app. This table stores Telegram references.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| transaction_id | FK → transactions CASCADE | |
| uploaded_by_user_id | FK → users nullable | |
| telegram_message_id | str nullable | Message ID in coordinator channel |
| telegram_file_id | str nullable | Telegram file ID for retrieval |
| telegram_chat_id | str nullable | Chat where photo was sent |
| caption | str nullable | |
| uploaded_at | datetime tz | |

When in-app upload is added in a future version: add `file_url` column and update upload handlers. Telegram fields remain for backward compatibility.
