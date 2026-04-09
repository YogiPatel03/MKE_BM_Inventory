# User Manual

Cabinet Inventory is a web app for tracking physical items stored in cabinets and bins — who has what, when it's due back, what was consumed, and how much was spent on restocking.

---

## Getting Started

### Logging in

Go to the web app URL and log in with the username and password your admin gave you. There is no self-registration — accounts are created by an administrator.

### Navigation

On desktop, the sidebar on the left links to every section. On mobile, use the tab bar at the bottom of the screen.

| Section | What it's for |
|---|---|
| Dashboard | Overview of active checkouts, overdue items, recent activity |
| Inventory | Browse cabinets and bins, see item availability |
| Transactions | Full history of checkouts and returns |
| Reports | Inventory health and expense tracking (coordinators) |
| Admin | User management (admins only) |
| Settings | Your profile and Telegram linking |

---

## Checking Out an Item

1. Go to **Inventory** and click a cabinet.
2. Find the item you want. The availability badge shows `available/total` units.
3. Click **Check out** next to the item (or on the item's detail page).
4. In the modal:
   - Set the quantity (defaults to 1).
   - Optionally set a due date.
   - Add a note if useful.
5. Click **Check out**. The item's availability updates immediately.

> Items marked **consumable** cannot be checked out. Use the **Use** button instead (see below).

> Items inside a **bin** cannot be individually checked out. The whole bin must be checked out as a unit (see Bin Checkout below).

---

## Consumable Items

Consumable items (e.g. batteries, tape, paper) are used up rather than returned.

- They show a **Use** button (flame icon) in the cabinet view and on their detail page.
- Clicking **Use** opens a form where you enter the quantity consumed and an optional note.
- Stock is reduced **permanently** — there is no return step.

To restock a consumable, a coordinator logs a **Purchase** (see Purchases section).

---

## Bin Checkout

Some items are organized inside bins and must be checked out as a group.

1. Open a cabinet that has bins.
2. Click **Check out bin** next to the bin you want.
3. Enter optional notes and confirm.
4. All items inside the bin are checked out together. They cannot be individually checked out while the bin is out.

To return: click **Return bin** on the same bin when it's back.

---

## Returning an Item

### From the Transactions page

1. Go to **Transactions**.
2. Find your checked-out item (status: **Checked out** or **Overdue**).
3. Click **Return**. The item is marked returned and availability is restored.

### From the Dashboard

The Recent Transactions section on the Dashboard also shows Return buttons for your active checkouts.

---

## Requesting an Item (USER role)

If you don't have permission to check out an item directly, submit a request:

1. On the item's detail page, click **Request**.
2. Enter the quantity and an optional reason.
3. A coordinator will review and approve or deny the request via the web app or Telegram.

When approved, the checkout is created automatically and you will be notified via Telegram (if your account is linked).

---

## Overdue Items

If you have a checkout past its due date, it will appear with an **Overdue** badge. You can still return it normally.

You'll receive a Telegram reminder if your Telegram account is linked.

---

## Condition Photos (via Telegram)

When you return an item, the Telegram bot posts a message in the coordinator channel asking for a condition photo:

1. In the coordinator Telegram channel, find the bot's return notification.
2. **Reply to that message** with a photo attached.
3. The bot confirms receipt and records it.

> The photo must be a **reply** to the bot's specific message — not a new message — so the system can match it to the right transaction.

---

## Telegram Bot

### Linking your account

1. Go to **Settings** → **Link Telegram**.
2. Click **Generate link token**.
3. Copy the `/link <token>` command shown.
4. Open the Telegram bot and send that command.
5. The bot confirms the link.

### Bot commands

| Command | What it does |
|---|---|
| `/start` | Shows available commands |
| `/link <token>` | Links your Telegram account |
| `/myitems` | Lists items you currently have checked out |
| `/status <item name>` | Shows availability for an item |
| `/overdue` | Lists all overdue checkouts (coordinators+) |
| `/requests` | Lists pending requests (coordinators+) |
| `/approve <id>` | Approve a request (coordinators+) |
| `/deny <id> [reason]` | Deny a request (coordinators+) |

---

## QR Code Scanning

Each bin has a QR code that links directly to its checkout/return flow.

- Scan a bin's QR code with your phone's camera or a QR reader.
- **Coordinators** are taken directly to a checkout or return screen.
- **Users** are taken to a request submission form.

To view or print a bin's QR code, open the cabinet, click **QR** next to the bin label. From the modal you can download as PNG or SVG, or print.

---

## Roles

Your role controls what you can do in the system.

| Role | What you can do |
|---|---|
| **USER** | Check out and return items for yourself. Submit requests. View your own transactions. |
| **GROUP_LEAD** | Everything a USER can do, plus process checkouts/returns for other users, view all transactions, approve requests. |
| **COORDINATOR** | Everything a GROUP_LEAD can do, plus manage cabinets, bins, items, log purchases, adjust stock. |
| **ADMIN** | Everything, plus create and manage user accounts and assign roles. |

---

## Admin: Managing Users

Go to **Admin** (only visible to admins).

### Creating a user

1. Click **Create user**.
2. Fill in full name, username, password, and role.
3. Optionally add their Telegram handle (without the `@`).
4. Click **Create user**.

To deactivate a user, edit them and uncheck **Active account**. Deactivated users cannot log in but their transaction history is preserved.

---

## Admin: Managing Inventory

Inventory management is available to COORDINATORs and ADMINs.

### Adding a cabinet

Go to **Inventory** → **Add Cabinet**.

### Adding a bin

1. Open a cabinet.
2. Click **Add Bin**.
3. Enter a label and optional location note.

### Adding an item

1. Open a cabinet.
2. Click **Add Item**.
3. Enter name, total quantity, condition, and optional SKU.
4. Check **Consumable** if the item is used up rather than returned.
5. Set a **Unit price** if you want expense tracking for this item.
6. Optionally assign it to a bin.

### Adjusting stock manually

On an item's detail page, coordinators see a **Adjust stock** button:
- Enter a delta (positive to add, negative to remove) and a reason (Restock, Damaged, Lost, Correction, Audit, Other).
- Stock adjustments are logged for audit purposes.

### Moving items or bins

- On an item's detail page, click **Move** to move it to a different cabinet or bin.
- On a cabinet page, click **Move bin** next to a bin to move the entire bin (and all its items) to another cabinet.

---

## Purchases (Restocking)

When you buy more of an item, log a purchase:

1. Go to the item's detail page and click **Log Purchase** (or use the purchases section).
2. Enter quantity, unit price, total price, vendor, and optional notes.
3. Click **Submit**.

After logging a purchase, the Telegram bot will:
- Post a message in the coordinator channel asking for a receipt photo
- DM you directly (if your Telegram is linked) reminding you to submit the receipt

To submit the receipt: reply to the bot's coordinator channel message with a photo.

---

## Reports

Available to coordinators and admins. Go to **Reports**.

### Inventory Status

Shows total items, checked-out count, overdue count, and low-stock items (those with 2 or fewer units available).

### Expense Report

Shows spending by period (this month, year-to-date, or custom date range):

- **Purchases tab** — spending by item for the selected period (restocking costs)
- **Usage tab** — estimated cost of consumables consumed, using historical purchase prices

Use the **Filter by item** dropdown to focus on a single item.

---

## Tips

- **Search**: On the Inventory page, use the search bar to filter items by name.
- **Item history**: Click any item name to see its full transaction, usage, and purchase history.
- **Filters**: On the Transactions page, filter by status (Checked out, Overdue, Returned, Cancelled).
- **Due dates**: Optional but recommended — they enable overdue detection and Telegram reminders.
