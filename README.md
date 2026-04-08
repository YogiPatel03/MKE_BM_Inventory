# Cabinet Inventory System

A production-ready inventory management system for tracking items stored in cabinets and bins.
Includes a web frontend, REST API backend, and a Telegram bot for notifications and lookups.

## Quick Start

See [docs/local-dev.md](docs/local-dev.md) for full setup instructions.

```bash
# Clone and setup
git clone <your-repo-url>
cd cabinet-inventory

# Backend
cd backend
cp .env.example .env   # fill in values
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
cp .env.example .env
npm install
npm run dev
```

## Architecture

- **Backend:** Python + FastAPI + SQLAlchemy 2.0 (async) + Alembic
- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS + TanStack Query
- **Database:** PostgreSQL (Neon.tech free tier)
- **Telegram bot:** python-telegram-bot v21, webhook mode
- **Hosting:** Render.com (backend) + Vercel (frontend)
- **CI/CD:** GitHub Actions

## Docs

| Doc | Description |
|---|---|
| [architecture.md](docs/architecture.md) | System overview and service interactions |
| [domain-model.md](docs/domain-model.md) | All entities, fields, and relationships |
| [roles-permissions.md](docs/roles-permissions.md) | RBAC role definitions |
| [telegram-bot.md](docs/telegram-bot.md) | Bot commands and integration |
| [photo-proof-flow.md](docs/photo-proof-flow.md) | Telegram-assisted proof workflow |
| [deployment.md](docs/deployment.md) | Production deployment guide |
| [local-dev.md](docs/local-dev.md) | Local development setup |
| [cost-notes.md](docs/cost-notes.md) | Cost breakdown and upgrade paths |

## Roles

| Role | Description |
|---|---|
| ADMIN | Full system access, manages users |
| COORDINATOR | Manages inventory, processes all transactions |
| GROUP_LEAD | Processes transactions, views all history |
| USER | Checks out and returns items |

## License

Internal use only.
