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
- **Resume analysis** — Upload PDF, extract skills, compare to positions with match score and bar charts. Optional LLM summary (Ollama) for AI-generated career advice.
- **Keycloak auth** — Optional login; protected endpoints (import, resume, backup) when `KEYCLOAK_URL` is set.
- **User & resume history** — Authenticated users get resume analyses persisted with extracted keywords.
- **Dark mode** — UI theme toggle.
- **API v1** — REST under `/api/v1/` with standardized error shape `{ error: { code, message, details? } }`.

---

## Tech stack

| Layer    | Stack |
|----------|--------|
| Backend  | FastAPI 2.x, SQLAlchemy 2, Celery (eager by default, no Redis required for dev), PostgreSQL |
| Frontend | React 19, TypeScript, Vite 7, MUI, Tailwind CSS, Recharts, React Router |
| Run      | Docker Compose (Postgres + backend + frontend + Keycloak + Ollama) |

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
- **Keycloak:** http://localhost:8080 (admin/admin)

Default DB: `postgresql://jobseeker:jobseeker@postgres:5432/jobseeker` (inside Compose).

**Keycloak setup:** See [docs/KEYCLOAK_SETUP.md](docs/KEYCLOAK_SETUP.md). When `KEYCLOAK_URL` is set, import, resume, and backup require login.

**LLM summary (optional):** After resume analysis, users can click "Generate AI summary" to get an AI-generated career advice. Requires Ollama running with a model. The `./scripts/test-and-build.sh` script pulls the model automatically. For manual `docker compose up`, run:

```bash
docker compose exec ollama ollama pull tinyllama
```

Default model is `tinyllama` (1.1B, smallest working). For better quality, use `phi3:mini` or `llama3.2:3b` and set `LLM_MODEL` accordingly. On small containers, summary may take 60-90s; increase `LLM_SUMMARIZE_TIMEOUT` if needed. To disable summaries, unset `LLM_URL` in the backend environment.

### Local development

**Backend**

Run from the **backend** directory so Python finds the `app` package (otherwise you get `ModuleNotFoundError: No module named 'app'`):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://jobseeker:jobseeker@localhost:5432/jobseeker
# Start Postgres (e.g. docker compose up postgres -d)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

From project root you can use: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir backend`

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

Frontend proxies `/api` to `http://localhost:8000` (see `frontend/vite.config.ts`).

### Test and build pipeline

```bash
./scripts/test-and-build.sh
```

Runs backend + frontend tests, then `docker compose up --build -d`, then pulls the Ollama model for resume summaries. One command to run the full stack. See [docs/TESTING_PLAN.md](docs/TESTING_PLAN.md).

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

| Variable           | Description |
|--------------------|-------------|
| `DATABASE_URL`     | PostgreSQL URL (required for backend). |
| `ENRICH_ON_IMPORT` | When set (`1`, `true`, `yes`), NoFluffJobs import fetches each job page for description and nice-to-have skills. Slower but richer data. |
| `LLM_URL`          | Ollama API URL (e.g. `http://ollama:11434`). If unset, resume summaries are disabled. |
| `LLM_MODEL`             | Model name for summarization (default: `tinyllama`). Use `phi3:mini` or `llama3.2:3b` for better quality. |
| `LLM_TIMEOUT`           | Timeout in seconds for LLM requests (default: 30). |
| `LLM_SUMMARIZE_TIMEOUT` | Timeout for on-demand summarize (default: 90). Increase on small containers. |

Celery runs in eager mode by default so imports work without Redis; optional Redis can be added for real background workers.

---

## License

MIT (or your choice).
