# User Manual

Cabinet Inventory is a web app for tracking physical items stored in cabinets and bins — who has what, when it's due back, and what condition it was returned in.

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
| Admin | User management (admins only) |
| Settings | Your profile and Telegram linking |

---

## Checking Out an Item

1. Go to **Inventory** and click a cabinet.
2. Find the item you want. The availability badge shows `available/total` units.
3. Click **Check out** next to the item (or on the item's detail page).
4. In the modal:
   - Set the quantity (defaults to 1).
   - Optionally set a due date — this is when you plan to return it.
   - Add a note if useful (project name, purpose, etc.).
5. Click **Check out**. The item's availability updates immediately.

> Items with 0 available cannot be checked out. Contact a coordinator if you need an item that shows as out of stock.

---

## Returning an Item

### From the Transactions page

1. Go to **Transactions**.
2. Find your checked-out item. Transactions with status **Checked out** or **Overdue** have a **Return** button.
3. Click **Return**. The item is marked returned and its availability is restored.

### From the Dashboard

The Recent Transactions section on the Dashboard also shows Return buttons for your active checkouts.

---

## Overdue Items

If you have a checkout past its due date, it will appear with an **Overdue** badge. You can still return it normally — click the Return button.

You'll receive a Telegram reminder if your Telegram is linked (see below).

---

## Telegram Bot

The Telegram bot lets you check your items, look up availability, and receive notifications — without opening the web app.

### Linking your account

1. Go to **Settings** → **Link Telegram**.
2. Click **Generate link token**.
3. Copy the `/link <token>` command shown.
4. Open the Telegram bot and send that command.
5. The bot confirms the link.

Once linked, you'll receive:
- A direct message when one of your checkouts goes overdue
- Prompts to submit a condition photo after returning an item

### Bot commands

| Command | What it does |
|---|---|
| `/start` | Shows available commands |
| `/link <token>` | Links your Telegram account to your web app account |
| `/myitems` | Lists items you currently have checked out |
| `/status <item name>` | Shows availability for an item (partial name works) |
| `/overdue` | Lists all overdue checkouts (coordinators and admins only) |

---

## Condition Photos (via Telegram)

When you return an item, the bot posts a message in the coordinator channel asking for a condition photo. To submit one:

1. In the coordinator Telegram channel, find the bot's return notification message.
2. **Reply to that message** with a photo attached.
3. The bot confirms receipt and records it against the return.

> The photo must be a reply to the bot's specific message — not a new message — so the system can match it to the right transaction.

---

## Roles

Your role controls what you can do in the system.

| Role | What you can do |
|---|---|
| **USER** | Check out and return items for yourself. View your own transaction history. |
| **GROUP_LEAD** | Everything a USER can do, plus process checkouts/returns for other users, and view all transactions. |
| **COORDINATOR** | Everything a GROUP_LEAD can do, plus create and manage cabinets, bins, and items. |
| **ADMIN** | Everything, plus create and manage user accounts and assign roles. |

---

## Admin: Managing Users

Go to **Admin** (only visible to admins).

### Creating a user

1. Click **Create user**.
2. Fill in full name, username, password, and role.
3. Optionally add their Telegram handle (without the `@`).
4. Click **Create user**.

The user can now log in with the username and password you set. They should link their Telegram account from Settings after their first login.

### Editing a user

Click **Edit** on any user row to change their name, role, Telegram handle, or active status.

To deactivate a user (e.g. they've left the team), edit them and uncheck **Active account**. Deactivated users cannot log in but their transaction history is preserved.

---

## Admin: Managing Inventory

Inventory management is available to COORDINATORs and ADMINs.

### Adding a cabinet

1. Go to **Inventory** → **Add Cabinet**.
2. Enter a name, an optional location (e.g. "Room 204, shelf B"), and an optional description.
3. Click **Create cabinet**.

### Adding a bin

1. Open a cabinet.
2. Click **Add Bin**.
3. Enter a label (e.g. "A1") and an optional location note.
4. Click **Create bin**.

Bins are sub-containers inside a cabinet. They're optional — items can also sit directly in a cabinet.

### Adding an item

1. Open a cabinet.
2. Click **Add Item**.
3. Enter the name, total quantity, condition, and optional SKU.
4. Optionally assign it to a bin within the cabinet.
5. Click **Add item**.

The item's available quantity starts equal to total quantity. It decreases when items are checked out and increases when they're returned.

---

## Tips

- **Search**: On the Inventory page, use the search bar to filter cabinets by name or location.
- **Item history**: Click any item name to open its detail page, which shows its full transaction history.
- **Filters**: On the Transactions page, use the status dropdown to filter by Checked out, Overdue, Returned, or Cancelled.
- **Due dates are optional** but recommended — they enable overdue detection and Telegram reminders.
