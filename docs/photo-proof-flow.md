# Photo Proof Flow

## Decision: Telegram-Assisted Proof Workflow (No In-App Storage)

**v1 does not include web-based photo uploads.**

### Why Not In-App Storage?

The $0/month target combined with photos being optional made in-app storage a bad tradeoff:

| Option | Cost | Complexity | Verdict |
|---|---|---|---|
| Cloudinary free (25 GB) | $0 but limited | Add SDK, upload endpoint, signed URLs | Adds service dependency for optional feature |
| Supabase Storage free (1 GB) | $0 but limited | Similar complexity | Second external service |
| Render disk (free) | Not persistent across deploys | Unreliable | Not viable |
| GitHub LFS | Not for dynamic uploads | Not applicable | Not viable |
| **Telegram-assisted flow** | **$0, forever** | **Already integrated** | **Winner** |

The Telegram bot is already required infrastructure. Sending photos there is natural for this kind of small team. Telegram persists photos indefinitely. The `TransactionPhoto` table stores Telegram file IDs as references.

### How the Flow Works

**Step 1: Return is logged in the web app**

User clicks "Return" → submits the return form (no photo). Backend:
1. Marks transaction RETURNED
2. Increments `Item.quantity_available`
3. Sets `Transaction.photo_requested_via_telegram = True`

**Step 2: Bot sends a photo request**

Immediately after the return is committed:
```
telegram_service.notify_return_and_request_photo(transaction)
```

Bot posts in the coordinator channel:
```
✅ Return logged #42
Item: Safety Goggles × 2
Returned by: @alice

📷 No photo was attached. @alice, please reply to this message
with a condition/return photo for the record.
```

**Step 3: User provides the photo in Telegram**

Alice replies in the Telegram thread with a photo. The coordinator can see it inline.
Telegram stores the photo on their servers indefinitely.

**Step 4 (optional): Record the Telegram proof**

If needed, a coordinator can record the Telegram proof in the system:
- When a user replies with a photo in the coordinator chat, the bot captures the `telegram_file_id` and `telegram_message_id`
- These are saved to `TransactionPhoto` table
- The web app can display "Proof provided via Telegram" with a reference

*(This is implemented as an optional enhancement — the bot handler for photo replies in the coordinator channel is stubbed but not yet active. See `app/bot/handlers.py`.)*

### What the UI Shows

The return `TransactionRow` component shows:
```
📷 Photo requested via Telegram
```
...when `transaction.photo_requested_via_telegram = True` and the status is RETURNED.

### Upgrading to In-App Uploads

When you want to add in-app photos (e.g. via Cloudinary):
1. Add `file_url` column to `transaction_photos` via Alembic migration
2. Add a `CLOUDINARY_URL` env var
3. Add an upload endpoint in the `transactions` router
4. Add a file input to `ReturnModal.tsx`
5. The `TransactionPhoto` model already exists; just populate `file_url` instead of the Telegram fields

The Telegram fallback continues to work alongside in-app uploads.

### Operational Guidelines

- Coordinators should check the Telegram group daily for unanswered photo requests
- The bot's photo requests appear as replies in the coordinator thread, making them easy to track
- Users are @mentioned directly so they receive a Telegram notification
- If a user is not on Telegram, the coordinator can document the condition in the transaction notes instead
