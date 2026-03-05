# Job Seeker Tracker

Track job offers from **JustJoin.it** and **NoFluffJobs**, with skills analytics, salary normalization, bulk import, and backup. FastAPI + React + PostgreSQL + Celery.

---

## Features

- **Job list** — Filter by status, saved, seniority, category, work type, location; pagination; duplicate grouping; alternate listings (same job on multiple sites).
- **Job detail** — View/edit job, mark saved, see detected skills and alternate URLs.
- **Bulk import** — Import from JustJoin.it and NoFluffJobs with resumable progress; start/cancel per source or all.
- **Analytics / dashboard** — Top skills, salary stats, charts (Recharts).
- **Skills** — Detected skills per job; summary and match endpoints.
- **Backup** — Download database as `.sql` (PostgreSQL `pg_dump`).
- **Dark mode** — UI theme toggle.
- **API v1** — REST under `/api/v1/` with standardized error shape `{ error: { code, message, details? } }`.

---

## Tech stack

| Layer    | Stack |
|----------|--------|
| Backend  | FastAPI 2.x, SQLAlchemy 2, Celery (eager by default, no Redis required for dev), PostgreSQL |
| Frontend | React 19, TypeScript, Vite 7, MUI, Tailwind CSS, Recharts, React Router |
| Run      | Docker Compose (Postgres + backend + frontend) |

---

## Quick start

### With Docker (recommended)

```bash
# From project root
docker compose up --build
```

- **Frontend:** http://localhost:5173  
- **Backend API:** http://localhost:8000  
- **API docs:** http://localhost:8000/api/v1/docs  

Default DB: `postgresql://jobseeker:jobseeker@postgres:5432/jobseeker` (inside Compose).

### Local development

**Backend**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://jobseeker:jobseeker@localhost:5432/jobseeker
# Start Postgres (e.g. docker compose up postgres -d)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

Frontend proxies `/api` to `http://localhost:8000` (see `frontend/vite.config.ts`).

---

## API overview

| Area     | Base path           | Notes |
|----------|---------------------|--------|
| Jobs     | `/api/v1/jobs`      | CRUD, list with filters, parse URL, analytics, categories, seniorities, locations, top skills, duplicate check, recalculate salaries |
| Skills   | `/api/v1/skills`    | Summary, detected, match |
| Import   | `/api/v1/import`    | Status, start (all or per source), cancel |
| Backup   | `/api/v1/backup`    | POST create → download .sql |
| Health   | `/api/v1/health`    | `{"status":"ok"}` |

OpenAPI: `/api/v1/docs`, `/api/v1/redoc`, `/api/v1/openapi.json`.

---

## Tests

**Backend (pytest)**

```bash
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql://jobseeker:jobseeker@localhost:5432/jobseeker
pytest
```

**Frontend (Vitest + React Testing Library)**

```bash
cd frontend
npm install
npm run test
```

---

## Project layout

```
job-seeker/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app, CORS, routers
│   │   ├── database.py       # SQLAlchemy engine, session
│   │   ├── errors.py         # Standardized API error handlers
│   │   ├── celery_app.py     # Celery (eager by default)
│   │   ├── import_engine.py  # Bulk import state & recovery
│   │   ├── models/           # SQLAlchemy models, Pydantic schemas
│   │   ├── routers/          # jobs, skills, imports, backup
│   │   ├── parsers/          # JustJoin, NoFluffJobs scrapers
│   │   ├── services/         # e.g. currency normalization
│   │   └── migrations/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api/              # client, types
│   │   └── pages/            # JobList, JobDetail, Import, etc.
│   ├── package.json
│   ├── vite.config.ts
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
└── README.md
```

---

## Environment

| Variable       | Description |
|----------------|-------------|
| `DATABASE_URL` | PostgreSQL URL (required for backend). |

Celery runs in eager mode by default so imports work without Redis; optional Redis can be added for real background workers.

---

## License

MIT (or your choice).
