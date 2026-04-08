# Local Development

## Prerequisites

- Python 3.11+
- Node 20+
- Docker Desktop (for local Postgres) OR a Neon.tech account

## Option A: Docker Compose (recommended)

```bash
cd cabinet-inventory

# Start Postgres only
docker compose up db -d

# Backend
cd backend
cp .env.example .env
# Edit .env — DATABASE_URL and DATABASE_URL_SYNC should already point to Docker Postgres

python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

alembic upgrade head          # Run migrations
uvicorn app.main:app --reload  # API at http://localhost:8000

# Frontend (new terminal)
cd ../frontend
cp .env.example .env
npm install
npm run dev                   # UI at http://localhost:5173
```

## Option B: Full Docker Compose

```bash
docker compose up --build
# API: http://localhost:8000
# DB: localhost:5432
```

Note: In this mode, the backend does NOT hot-reload. Use Option A for development.

## Seed an Admin Account

After running migrations, create your first admin user manually:

```python
# Run from backend/ with venv active
python - <<'EOF'
import asyncio
from app.database import AsyncSessionLocal
from app.models import User, Role
from app.core.security import hash_password
from sqlalchemy import select

async def seed():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Role).where(Role.name == "ADMIN"))
        role = result.scalar_one()
        user = User(
            full_name="Admin User",
            username="admin",
            password_hash=hash_password("changeme123"),
            role_id=role.id,
        )
        db.add(user)
        await db.commit()
        print(f"Admin user created: admin / changeme123")

asyncio.run(seed())
EOF
```

## Environment Variables

See `backend/.env.example` for all variables with descriptions.

Required for local dev:
- `DATABASE_URL` — async Postgres URL
- `DATABASE_URL_SYNC` — sync Postgres URL (for Alembic)
- `SECRET_KEY` — any long random string

Optional for local dev (bot won't send messages without these):
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `TELEGRAM_COORDINATOR_CHAT_ID`

## Running Tests

```bash
cd backend
pip install aiosqlite  # SQLite driver for in-memory test DB
pytest tests/ -v
```

## API Docs

FastAPI generates interactive docs at:
- Swagger: http://localhost:8000/api/docs (disabled in production)
- Health check: http://localhost:8000/health

## Telegram Bot (local)

The bot uses webhook mode in production. For local development, the easiest approach is to use [ngrok](https://ngrok.com) to expose your local server:

```bash
ngrok http 8000
# Copy the https URL, e.g. https://abc123.ngrok.io

# Register the webhook manually
curl -X POST "https://api.telegram.org/bot{TOKEN}/setWebhook" \
  -d "url=https://abc123.ngrok.io/api/telegram/webhook/{TELEGRAM_WEBHOOK_SECRET}"
```

Or, for simpler local testing, temporarily switch to polling by adding a polling startup task (not recommended for production).
