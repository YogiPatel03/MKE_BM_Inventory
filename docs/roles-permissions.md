# Roles and Permissions

## Role Definitions

### ADMIN
Full system access. The only role that can create and manage user accounts.

**Can do everything:**
- Create, edit, deactivate users
- Assign any role to any user
- Manage cabinets, bins, items
- Process checkouts and returns for any user
- View all transaction history
- View audit logs
- Cancel any transaction

**Restrictions:** None.

---

### COORDINATOR
Manages inventory and processes transactions. Cannot manage user accounts.

**Can:**
- Create, edit, delete cabinets
- Create, edit, delete bins
- Create, edit, deactivate items
- Process checkouts and returns for any user
- View all transaction history
- View audit logs
- Cancel transactions

**Cannot:**
- Create or edit user accounts
- Assign roles

---

### GROUP_LEAD
Can process transactions for any user and view system-wide history. Cannot manage inventory structure.

**Can:**
- Check out items for themselves
- Return items for themselves
- Process checkouts and returns for any user
- View all transaction history and audit logs

**Cannot:**
- Create/edit cabinets, bins, or items
- Create or edit user accounts

---

### USER
Basic access. Can only manage their own transactions.

**Can:**
- Check out items for themselves
- Return their own items
- View their own transaction history

**Cannot:**
- Process transactions for other users
- View other users' transactions
- Manage inventory, cabinets, bins
- Manage users or roles

---

## RBAC Implementation

Permissions are checked in two places:

1. **Route-level guards** (`app/core/permissions.py`)
   - `require_manage_inventory(user)` — raises 403 if role lacks permission
   - `require_manage_cabinets(user)`
   - `require_manage_bins(user)`
   - `require_manage_users(user)`
   - `require_process_any_transaction(user)`
   - `require_view_all_transactions(user)`

2. **Data-level filtering** (in routers)
   - `GET /api/transactions` filters to `user_id = current_user.id` unless `can_view_all_transactions`

3. **Helper function**
   - `can_process_transaction_for(actor, target_user_id)` — returns True if actor is allowed to act on behalf of target_user_id (always True for own transactions; True for COORDINATOR/ADMIN for any user)

## Role Seeding

Roles are created in the initial Alembic migration (`001_initial_schema.py`).
They are immutable records — the permission flags define what each role can do.
To change a role's permissions, create a new Alembic migration that updates the flags.

## Approvals

In v1, there is no explicit approval workflow. The intent of `can_process_any_transaction` is that coordinators and group leads can process checkouts on behalf of users (e.g. "I'm checking this out for Bob"). There is no pending/approval state on transactions in v1.

If an approval workflow is needed in the future:
- Add a `PENDING` status to `TransactionStatus`
- Add an `approved_by_user_id` field to `Transaction`
- Add an approval endpoint to the transactions router
