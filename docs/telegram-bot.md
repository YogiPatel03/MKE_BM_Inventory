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

### Checklist commands

| Command | Who can use | Description |
|---|---|---|
| `/tasks` | Linked users | Current week's task list for your group (or the topic's group) |
| `/mytasks` | Linked users | Tasks assigned to you or to everyone in your group |
| `/task <id>` | Linked users | Read-only task details; never modifies DB state |
| `/done <id> [note]` | Assigned users, coordinators | Mark a task complete; note stored in completion_notes |
| `/undo <id> [reason]` | Coordinators, group leads, task completer | Mark a task incomplete again |
| `/claim <id>` | Coordinators, assigned group leads | Assign the task to yourself |
| `/unclaim <id>` | Task assignee, coordinators, assigned group leads | Remove your assignment |
| `/assign <id> me` | Coordinators, assigned group leads | Same as /claim |
| `/assign <id> everyone` | Coordinators, assigned group leads | Set task to shared (everyone) responsibility |
| `/assign <id> @username` | Coordinators, assigned group leads | Assign to a linked Telegram user; DMs them |

### Inventory commands

| Command | Who can use | Description |
|---|---|---|
| `/start` | Anyone | Shows help and command list |
| `/help` | Anyone | Full command list with permission notes |
| `/whereami` | Anyone (usually admins) | Prints this chat's IDs for Render env var setup |
| `/whoami` | Anyone | Shows linked account info, or explains how to link |
| `/link <token>` | Anyone (**DM only**) | Links Telegram account to system user |
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
4. User copies the token and sends `/link <token>` **in a private DM with the bot**
5. Bot looks up the user by `telegram_link_token`, sets `User.telegram_chat_id = message.from.id`, clears the token
6. Bot confirms: "✅ Account linked!"

The token is one-time: it is cleared after use and cannot be reused.

**Important:** `/link` only works in a private DM. Running it in a group or topic will be rejected without consuming the token.

## Identity Contract

`message.chat.id` — where the bot replies (group or supergroup ID when in a group/topic).  
`message.from.id` — the individual who sent the command (always the personal Telegram ID).

In a **private DM** these are equal. In a **group or topic**, `chat.id` is the group's ID while `from.id` is the individual user's ID. The bot always:
- resolves the app user by `message.from.id` (not `chat.id`)
- replies to `message.chat.id` (the group/topic chat)
- stores `User.telegram_chat_id = message.from.id` (personal DM ID)

This means group commands resolve the correct user and personal DMs always reach the individual.

## Topic / Forum Support

Telegram forum topics do **not** have their own chat IDs. A topic message uses the same supergroup `chat_id` plus a `message_thread_id`. The bot:

1. Reads `message.message_thread_id` from incoming updates.
2. Passes it to `bot.send_message(message_thread_id=...)` so replies stay inside the same topic.
3. Uses `TELEGRAM_GROUP_TOPIC_THREAD_IDS` to route outbound group notifications to the correct topic.

### How to find IDs for Render env vars

1. Add the bot to your supergroup (or topic).
2. Send `/whereami` inside the chat or topic where you want the bot to send messages.
3. The bot replies with:
   - `chat_id` — use this as `TELEGRAM_COORDINATOR_CHAT_ID`
   - `message_thread_id` — the thread ID for this specific topic (absent if not a topic)
   - `actor_telegram_id` — your personal Telegram ID
4. To route coordinator alerts (checkouts, returns, requests, etc.) to a specific topic (e.g. "Inventory"), run `/whereami` inside that topic and copy its `message_thread_id` → set as `TELEGRAM_COORDINATOR_THREAD_ID`.
5. Repeat step 2–3 for each group checklist topic you want to map.
6. Build the JSON mapping (see below) and set `TELEGRAM_GROUP_TOPIC_THREAD_IDS` in Render.

### Environment Variables

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `TELEGRAM_WEBHOOK_SECRET` | Random secret in the webhook URL |
| `TELEGRAM_COORDINATOR_CHAT_ID` | Supergroup chat ID for coordinator alerts (e.g. `-100xxxxxxxxxx`) |
| `TELEGRAM_COORDINATOR_THREAD_ID` | Optional `message_thread_id` for the coordinator "Inventory" topic. When set, all coordinator alerts (checkouts, returns, requests, low-stock, etc.) are posted into that forum topic instead of General. Get the value by running `/whereami` inside the Inventory topic. Leave blank to post to General. |
| `TELEGRAM_GROUP_TOPIC_THREAD_IDS` | JSON mapping of group name → `message_thread_id` for group checklist topics (independent of `TELEGRAM_COORDINATOR_THREAD_ID`) |
| `APP_TIMEZONE` | Timezone for display; Sunday scheduler jobs run at `America/Chicago` (hardcoded). |

**TELEGRAM_GROUP_TOPIC_THREAD_IDS example:**
```
{"SHISHU_MANDAL":12,"GROUP_1":34,"GROUP_2":56,"GROUP_3":78}
```

- Replace the numbers with the actual `message_thread_id` values from `/whereami`.
- If a group is missing from the mapping, notifications for that group fall back to the coordinator chat without a thread (and a warning is logged).
- Invalid JSON does not crash app startup — it logs a warning and treats the mapping as empty.

### Migrated supergroups

If Telegram migrates a regular group to a supergroup, the `chat_id` changes. Run `/whereami` again after migration and update `TELEGRAM_COORDINATOR_CHAT_ID`.

## Notification Events

### Checkout notification
Sent to the coordinator channel and as a DM to the borrower.
```
📦 Checkout #42
Item: Safety Goggles × 2
User: @alice
Due: Jun 15, 2025
```

### Return notification + photo request
Sent to the coordinator channel when an item is returned. The bot's message_id is stored on the `Transaction` so a photo reply can be matched back to it.
```
✅ Return logged #42
Item: Safety Goggles × 2
Returned by: @alice

📷 No photo was attached. @alice, please reply to this message
with a condition/return photo for the record.
```

### Purchase notification + receipt request
Sent to the coordinator channel and as a DM to the purchaser. The coordinator channel message_id is stored on the `ReceiptRecord` for photo matching.

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
Sent hourly when the scheduler detects overdue items.
- **DM** to the borrower (if `telegram_chat_id` is linked)
- **Coordinator channel** post listing the item and borrower

### Request notification
Sent to the coordinator channel when a user submits an inventory request.
```
📋 New Request #3
From: charlie
Item: Power Drill
Reason: Workshop session

/approve 3  |  /deny 3
```

### Personal DMs

Checkout, return, overdue, and request approved/denied notifications that go to individual users are always sent to `User.telegram_chat_id` — the personal DM chat ID stored at linking time. These are never routed to group topics.

## Photo Reply Handling

The bot dispatches photo replies to two handlers (tried in order):

1. **`handle_receipt_photo_reply`** — matches `reply_to_message.message_id` against `ReceiptRecord.telegram_request_message_id`. If found, sets `ReceiptRecord.telegram_file_id` and confirms receipt.

2. **`handle_photo_reply`** — matches against `Transaction.photo_request_message_id`. If found, creates a `TransactionPhoto` record.

Both handlers only process photos sent in the coordinator channel.

## Security

- Webhook URL contains a secret path segment (`TELEGRAM_WEBHOOK_SECRET`)
- The router returns 403 if the secret doesn't match
- `/link` only works in a private DM — group/topic attempts are rejected without consuming the token
- The rejection message does not echo any part of the submitted token
- Bot commands that require elevated permissions check `User.role` after looking up the user by `message.from.id`
- Unique constraint on `User.telegram_chat_id` prevents two accounts sharing one Telegram identity

## Webhook vs Polling Decision

**Webhook** is used for production because:
- No continuous polling loop required (lower resource use)
- Lower latency for message delivery
- Cleaner integration with the FastAPI async event loop

**Polling** is easier for local development. See `docs/local-dev.md` for the ngrok-based local webhook setup.

## Scheduled Sunday messages

Two APScheduler cron jobs (timezone: `America/Chicago`) run automatically:

| Job | Time | What it sends |
|---|---|---|
| `sunday_checklist_morning` | Sunday 9:00 AM Central | Full current-week task list for each group |
| `sunday_checklist_reminder` | Sunday 7:00 PM Central | Incomplete tasks only; also DMs users with specifically-assigned incomplete tasks |

Both jobs send to each group's coordinator topic thread (via `TELEGRAM_GROUP_TOPIC_THREAD_IDS`), falling back to the coordinator chat without a thread if a group is not mapped. Neither job creates a new weekly checklist — that is the Monday 6:00 AM job's responsibility.

**Sunday evening DM rule:** Only users with a non-null `assignee_id` on an incomplete task receive a DM. Tasks with `assignee_id IS NULL` (everyone tasks) do not trigger individual DMs.

## Command examples

```
/tasks                        — group 1 task list (or detected from topic)
/mytasks                      — your tasks + everyone tasks
/task 104                     — details for task #104
/done 104 tables are set up   — mark task 104 complete with note
/undo 104 forgot one table    — mark task 104 incomplete
/claim 104                    — assign task 104 to yourself
/unclaim 104                  — remove your claim on task 104
/assign 104 me                — same as /claim
/assign 104 everyone          — set task 104 to shared responsibility
/assign 104 @raj              — assign task 104 to linked user @raj
/requests                     — list pending requests
/approve 12                   — approve request #12
/deny 12 not enough stock     — deny request #12 with reason
/whereami                     — show chat_id and thread IDs for setup
```

## Manual QA checklist

1. DM bot with `/start`
2. DM bot with `/link <token>` (get token from Settings → Link Telegram)
3. Run `/whereami` in each group topic; copy the `message_thread_id` values
4. Set `TELEGRAM_GROUP_TOPIC_THREAD_IDS` env var and restart backend
5. Run `/tasks` in a Group 1 topic — verify Group 1 task list appears in that topic
6. Run `/mytasks` as a linked user — verify your assigned + everyone tasks appear
7. View a task with `/task <id>` — verify read-only details; check DB unchanged
8. Claim a task with `/claim <id>` — verify website shows your name as assignee
9. Mark task done with `/done <id> <note>` — verify website shows complete + note
10. Undo with `/undo <id>` — verify website shows incomplete again
11. Assign to everyone with `/assign <id> everyone` — verify website shows no assignee
12. Assign to `@username` with `/assign <id> @raj` — verify website shows Raj; confirm Raj receives DM
13. Try to manually complete an auto-generated return task — confirm it is blocked
14. Test `/approve <id>` and `/deny <id>` from Telegram — confirm website request page updates
15. Trigger a checkout and return — confirm personal DMs still arrive for those events
16. Wait until Sunday or trigger `_run_sunday_checklist_morning()` manually — confirm group messages sent

## Adding New Commands

1. Add a handler function in `app/bot/handlers.py` with signature `async def cmd_xxx(ctx: BotContext, db: AsyncSession) -> None`
2. Register it in the `handle_update()` dispatch block
3. Use `await _send(ctx.reply_chat_id, text, message_thread_id=ctx.message_thread_id)` so replies stay in the correct topic
4. For long messages, use `await _send_chunks(ctx.reply_chat_id, text, message_thread_id=ctx.message_thread_id)`
5. Add the command to BotFather via `/setcommands`
