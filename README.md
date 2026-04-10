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

## Inventory Hierarchy

```
Room  →  Cabinet  →  Bin  →  Item
                  →  Item (direct, no bin)
```

Rooms group cabinets by physical location (e.g. "Shishu Mandal", "Main Store Room").
All existing cabinets were auto-migrated into the "Shishu Mandal" room.

## Weekly Checklists

Each of the four groups (Shishu Mandal, Group 1, Group 2, Group 3) gets one checklist per week, auto-generated every Monday at 06:00.

- When a group member checks out an item or bin, a return task is automatically added to their group's checklist.
- When the item or bin is returned, the task is auto-completed.
- Coordinators and admins can add manual tasks and assign members.
- Telegram photo proof can be requested for return tasks.

Users must have their `group_name` field set (via Admin → Edit User) for auto-return tasks to appear.

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
| [implementation-summary.md](docs/implementation-summary.md) | Recent sprint: Rooms, Checklists, mobile nav, reports |

## Roles

| Role | Description |
|---|---|
| ADMIN | Full system access, manages users and rooms |
| COORDINATOR | Manages inventory, processes all transactions, views reports |
| GROUP_LEAD | Processes transactions, views all history |
| USER | Checks out and returns items; submits checkout requests |

## License

Internal use only.
