# Photo Proof Flow

## Decision: Telegram-Assisted Proof Workflow (No In-App Storage)

**v1 does not include web-based photo uploads for transaction condition photos.**

### Why Not In-App Storage?

The $0/month target combined with photos being optional made in-app storage a bad tradeoff:

| Option | Cost | Complexity | Verdict |
|---|---|---|---|
| Cloudinary free (25 GB) | $0 but limited | Add SDK, upload endpoint, signed URLs | Adds service dependency for optional feature |
| Supabase Storage free (1 GB) | $0 but limited | Similar complexity | Second external service |
| Render disk (free) | Not persistent across deploys | Unreliable | Not viable |
| **Telegram-assisted flow** | **$0, forever** | **Already integrated** | **Winner** |

The Telegram bot is already required infrastructure. Sending photos there is natural for this small team. Telegram persists photos indefinitely. References (`telegram_file_id`) are stored in the database.

---

## Flow 1: Return Condition Photos

**Step 1: Return is logged in the web app**

User clicks "Return" → submits the return form (no photo). Backend:
1. Marks transaction RETURNED
2. Increments `Item.quantity_available`
3. Sets `Transaction.photo_requested_via_telegram = True`

**Step 2: Bot sends a photo request to the coordinator channel**

```python
telegram_service.notify_return_and_request_photo(transaction)
```

The message_id of the bot's post is stored in `Transaction.photo_request_message_id`.

**Step 3: User replies with a photo in the coordinator channel**

The user replies **to that specific message** in the Telegram thread. The bot receives the update.

**Step 4: `handle_photo_reply` records the proof**

`handle_update` sees a photo + reply_to_message → tries `handle_receipt_photo_reply` first (no match) → calls `handle_photo_reply`:
- Matches `reply_to_message.message_id` to `Transaction.photo_request_message_id`
- Creates a `TransactionPhoto` record with `telegram_file_id` and `telegram_message_id`
- Clears `Transaction.photo_request_message_id`
- Sends confirmation: "📷 Photo recorded for return #42. Thanks!"

---

## Flow 2: Purchase Receipt Photos

**Step 1: Purchase is logged in the web app**

Coordinator clicks "Log Purchase" → submits the form. Backend:
1. Creates `PurchaseRecord`
2. Creates a placeholder `ReceiptRecord` (`telegram_file_id = NULL`, `notes = "Awaiting receipt via Telegram"`)
3. Sets `PurchaseRecord.receipt_id = placeholder.id`

**Step 2: Bot sends receipt request to group AND DMs the purchaser**

```python
telegram_service.notify_purchase_and_request_receipt(
    purchase_id, item_name, quantity,
    purchaser_name, purchaser_tg_handle, purchaser_chat_id
)
```

The coordinator channel message_id is stored in `ReceiptRecord.telegram_request_message_id`.

**Step 3: Purchaser replies with a photo in the coordinator channel**

**Step 4: `handle_receipt_photo_reply` records the receipt**

`handle_update` sees a photo + reply_to_message → tries `handle_receipt_photo_reply` first:
- Matches `reply_to_message.message_id` to `ReceiptRecord.telegram_request_message_id`
- Sets `ReceiptRecord.telegram_file_id`
- Updates `uploaded_via = "telegram"` and attribution (`uploaded_by_user_id`)
- Sends confirmation: "📄 Receipt recorded (#5). Thanks!"

---

## Handler Dispatch Order

Both flows use the same dispatch point in `handle_update`:

```python
if message.get("photo") and message.get("reply_to_message"):
    handled = await handle_receipt_photo_reply(message, chat_id, db)
    if not handled:
        await handle_photo_reply(message, chat_id, db)
    return
```

Receipt handler runs first. If no matching `ReceiptRecord` is found, the transaction handler runs.

---

## What the Web UI Shows

- Transaction rows show "📷 Photo requested via Telegram" when `photo_requested_via_telegram = True`
- Receipt records show whether a `telegram_file_id` has been received

---

## Upgrading to In-App Uploads

When you want to add in-app photos (e.g. via Cloudinary):
1. Add `file_url` column to `transaction_photos` via migration
2. Add a `CLOUDINARY_URL` env var
3. Add an upload endpoint in the `transactions` router
4. Add a file input to `ReturnModal.tsx`
5. For receipts: add file upload to the purchase log flow or `/api/purchases/receipts`

The Telegram fallback continues to work alongside in-app uploads.

---

## Operational Guidelines

- Coordinators should check the Telegram group for unanswered photo requests
- The bot @mentions the user directly in the coordinator channel post
- If a user is not on Telegram, document the condition in the transaction/purchase notes instead
