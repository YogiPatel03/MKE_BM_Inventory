# Telegram Bot

## Integration Model

The bot runs **inside the FastAPI process** — no separate worker, no separate service.

Telegram sends updates to a webhook URL:
```
POST /api/telegram/webhook/{TELEGRAM_WEBHOOK_SECRET}
```

The `telegram_webhook` router receives the update and calls `bot/handlers.py:handle_update()`.
Telegram calls are made via `python-telegram-bot` v21 (async).

## Commands

| Command | Who can use | Description |
|---|---|---|
| `/start` | Anyone | Shows help and command list |
| `/link <token>` | Anyone | Links Telegram account to system user |
| `/myitems` | Linked users | Shows currently checked-out items |
| `/overdue` | GROUP_LEAD+ | Lists all overdue checkouts |
| `/status <item name>` | Anyone | Checks availability of an item |
| `/requests` | COORDINATOR+ | Lists pending inventory requests |
| `/approve <id>` | COORDINATOR+ | Approves a request, creates Transaction |
| `/deny <id> [reason]` | COORDINATOR+ | Denies a request with optional reason |

## Account Linking Flow

1. User goes to the web app **Settings** → **Link Telegram**
2. Clicks **Generate Link Token** → GET `/api/users/me/link-token`
3. Backend generates a 32-byte URL-safe token stored in `User.telegram_link_token`
4. User copies the token and sends `/link <token>` to the bot
5. Bot looks up the user by `telegram_link_token`, sets `User.telegram_chat_id = chat_id`, clears the token
6. Bot confirms: "✅ Account linked!"

The token is one-time: it is cleared after use and cannot be reused.

## Notification Events

### Checkout notification
Sent to the coordinator channel when any checkout occurs.
```
📦 Checkout #42
Item: Safety Goggles × 2
User: @alice
Due: Jun 15, 2025
```

### Return notification + photo request
Sent to the coordinator channel when an item is returned via the web app. The bot's message_id is stored on the `Transaction` so that a photo reply can be matched back to it.
```
✅ Return logged #42
Item: Safety Goggles × 2
Returned by: @alice

📷 No photo was attached. @alice, please reply to this message
with a condition/return photo for the record.
```

### Purchase notification + receipt request
Sent **both** to the coordinator channel and as a **DM** to the purchaser when a purchase is logged. The coordinator channel message_id is stored on the `ReceiptRecord` placeholder so photo replies can be matched.

**Coordinator channel:**
```
🛒 Purchase logged #7
Item: AA Batteries × 24
By: @bob

📄 @bob, please reply to this message with a receipt photo or scan.
```

**DM to purchaser:**
```
🛒 You just logged a purchase of AA Batteries × 24 (#7).

📄 Please reply to the coordinator channel message with a receipt photo or scan.
```

### Overdue reminder
Sent hourly (when the scheduler detects overdue items).
- **DM** to the borrower (if `telegram_chat_id` is linked)
- **Coordinator channel** post listing the item and borrower

```
⚠️ Overdue item reminder
You have an overdue checkout: Safety Goggles × 2
Was due: Jun 10, 2025
Please return it as soon as possible.
```

### Request notification
Sent to the coordinator channel when a user submits an inventory request.
```
📋 New Request #3
From: charlie
Item: Power Drill
Reason: Workshop session

/approve 3  |  /deny 3
```

## Photo Reply Handling

The bot dispatches photo replies to two handlers (tried in order):

1. **`handle_receipt_photo_reply`** — matches `reply_to_message.message_id` against `ReceiptRecord.telegram_request_message_id`. If found, sets `ReceiptRecord.telegram_file_id` and confirms receipt.

2. **`handle_photo_reply`** — matches against `Transaction.photo_request_message_id`. If found, creates a `TransactionPhoto` record.

Both handlers only process photos sent in the coordinator channel.

## Security

- Webhook URL contains a secret path segment (`TELEGRAM_WEBHOOK_SECRET`)
- The router returns 403 if the secret doesn't match
- Bot commands that require elevated permissions check `User.role` after looking up the user by `telegram_chat_id`
- Unlinked users cannot use most commands

## Webhook vs Polling Decision

**Webhook** is used for production because:
- No continuous polling loop required (lower resource use)
- Lower latency for message delivery
- Cleaner integration with the FastAPI async event loop

**Polling** is easier for local development. See `docs/local-dev.md` for the ngrok-based local webhook setup.

## Adding New Commands

1. Add a handler function in `app/bot/handlers.py`
2. Register it in the `handle_update()` dispatch block
3. Add the command to BotFather via `/setcommands`
