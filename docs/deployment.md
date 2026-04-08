# Deployment

## Stack

| Component | Service | Cost |
|---|---|---|
| Frontend | Vercel | Free |
| Backend | Render.com (free tier) | Free* |
| Database | Neon.tech | Free |
| CI/CD | GitHub Actions | Free |

*Render free tier sleeps after 15 min inactivity. First request takes ~20-30s. Acceptable for a small internal tool.

---

## 1. Database — Neon.tech

1. Create account at neon.tech
2. Create a new project, choose the nearest region
3. Copy connection strings from the dashboard:
   - **Pooled connection** (for async app): use as `DATABASE_URL` (replace `postgresql://` with `postgresql+asyncpg://`)
   - **Direct connection** (for Alembic migrations): use as `DATABASE_URL_SYNC`

---

## 2. Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram: `/newbot`
2. Follow prompts, copy the bot token → `TELEGRAM_BOT_TOKEN`
3. Create or find your coordinator group chat
4. Add the bot to the group
5. Get the group's chat ID (use `@userinfobot` or check the Telegram API)
6. Set `TELEGRAM_COORDINATOR_CHAT_ID` to the group's chat ID (negative number for groups, e.g. `-100123456789`)

---

## 3. Backend — Render.com

1. Push your repo to GitHub
2. Go to render.com → New → Web Service
3. Connect your GitHub repo, select the `backend/` directory
4. Render will detect the `render.yaml` file automatically
5. Set environment variables in the Render dashboard (see `backend/.env.example`):
   - `DATABASE_URL`
   - `DATABASE_URL_SYNC`
   - `SECRET_KEY` (generate with: `python -c "import secrets; print(secrets.token_hex(32))"`)
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_WEBHOOK_SECRET` (generate same way)
   - `TELEGRAM_COORDINATOR_CHAT_ID`
   - `FRONTEND_URL` (your Vercel URL, set after step 4)
   - `BACKEND_URL` (your Render URL, e.g. `https://cabinet-inventory-api.onrender.com`)
   - `ENVIRONMENT=production`
6. Deploy

**Migration:** The `buildCommand` in `render.yaml` runs `alembic upgrade head` automatically before each deploy.

---

## 4. Frontend — Vercel

1. Go to vercel.com → New Project → Import Git Repository
2. Select your repo, set Root Directory to `frontend`
3. Set environment variables:
   - `VITE_API_BASE_URL=https://cabinet-inventory-api.onrender.com`
4. Deploy
5. Copy the Vercel URL (e.g. `https://cabinet-inventory.vercel.app`)
6. Update `FRONTEND_URL` in Render environment variables

---

## 5. GitHub Secrets (for GitHub Actions CI/CD)

In your GitHub repo → Settings → Secrets → Actions:

| Secret | Value |
|---|---|
| `RENDER_DEPLOY_HOOK_URL` | From Render dashboard → Settings → Deploy Hooks |
| `DATABASE_URL_SYNC` | For the backup job (use Neon's direct connection string) |

---

## 6. Telegram Webhook Registration

The webhook is auto-registered on startup in production (see `app/main.py` startup event). If you need to register it manually:

```bash
curl -X POST "https://api.telegram.org/bot{TOKEN}/setWebhook" \
  -d "url=https://your-backend.onrender.com/api/telegram/webhook/{TELEGRAM_WEBHOOK_SECRET}"
```

---

## Migrations

Alembic runs automatically on Render deploy. For manual migration:

```bash
# Local
DATABASE_URL_SYNC="postgresql://..." alembic upgrade head

# Generate new migration after model changes
alembic revision --autogenerate -m "description"
```

---

## Monitoring

- **Logs:** Render dashboard → Logs tab (real-time, 30-day retention on free tier)
- **Errors:** Sentry free tier (set `SENTRY_DSN` in environment)
- **Health check:** `GET /health` — returns `{"status": "ok"}`

---

## Upgrading Beyond Free Tier

| Pain point | Upgrade |
|---|---|
| Render cold starts | Render Starter $7/month (always-on) |
| Neon storage > 0.5 GB | Neon Launch $19/month (10 GB) |
| Need in-app photo uploads | Add Cloudinary free tier (25 GB) |
