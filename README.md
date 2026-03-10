# Job Seeker Tracker

> Full-stack job tracker for Polish IT market: scrape offers, match your resume with AI, and track applications. React 19, FastAPI, PostgreSQL, Elasticsearch RAG, Ollama/OpenAI.

A portfolio project for job seekers who want to aggregate positions from JustJoin.it and NoFluffJobs, track application status, and get AI-powered resume analysis. Upload a PDF resume to extract skills, match against imported jobs (keyword + optional semantic RAG), and generate career advice summaries via Ollama or OpenAI.

---

## Key Features

- **Job list & detail** — Filter by status, seniority, category, work type, location; pagination; duplicate grouping
- **Bulk import** — Scrape JustJoin.it & NoFluffJobs with Celery; resumable, per-source control
- **Resume analysis** — PDF upload, skill extraction, keyword + semantic (RAG) matching, AI summaries, hybrid job recommendations
- **AI configuration** — Switch Ollama/OpenAI; choose LLM and embedding models; ensure-model (pull on demand); inference metrics
- **Production deployment** — One-command deploy to Ubuntu via rsync + Docker Compose; ollama-init auto-pulls models
- **Analytics dashboard** — Top skills, salary stats, charts (Recharts)
- **Optional auth** — Keycloak; login for import, backup, saving resume analyses

---

## Architecture

### System Overview

```mermaid
flowchart TB
    subgraph client [Client]
        Browser[Browser]
    end

    subgraph compose [Docker Compose]
        subgraph core [Core Services]
            Frontend[Frontend\nNginx :80]
            Backend[Backend\nFastAPI :8000]
            Postgres[(PostgreSQL\n:5432)]
            Elasticsearch[(Elasticsearch\n:9200)]
            Ollama[Ollama\n:11434]
        end

        subgraph optional [Optional]
            Keycloak[Keycloak\n:8080]
        end
    end

    Browser -->|"HTTP /api"| Frontend
    Frontend -->|"proxy"| Backend
    Backend -->|"SQL"| Postgres
    Backend -->|"kNN search\nbulk index"| Elasticsearch
    Backend -->|"LLM + embeddings\nOllama or OpenAI"| Ollama
    Browser -.->|"OAuth"| Keycloak
    Backend -.->|"JWT validate"| Keycloak
```

### Resume Analysis Pipeline

```mermaid
flowchart TB
    subgraph user [User]
        UploadPDF[Upload PDF]
    end

    subgraph backend [Backend]
        ResumeRouter[Resume Router]
        PyPDF[PyPDF extract keywords]
        MatchJobs[match_jobs_to_skills]
        RAGCheck{RAG enabled?}
        EmbedService[Embedding Service]
        ESService[Elasticsearch kNN]
        MergeMatches[merge keyword + semantic\ndedupe, sort, limit]
        LLMService[LLM summarize\nOllama or OpenAI]
    end

    subgraph data [Data Layer]
        Postgres[(PostgreSQL)]
        ES[(Elasticsearch)]
        LLM[Ollama / OpenAI]
    end

    UploadPDF --> ResumeRouter
    ResumeRouter --> PyPDF
    PyPDF --> MatchJobs
    MatchJobs -->|"read jobs"| Postgres
    MatchJobs -->|"keyword matches"| MergeMatches
    ResumeRouter --> RAGCheck
    RAGCheck -->|"yes"| EmbedService
    EmbedService -->|"embed skills"| LLM
    EmbedService -->|"vectors"| ESService
    ESService -->|"kNN search"| ES
    ESService -->|"semantic matches"| MergeMatches
    RAGCheck -->|"no"| MergeMatches
    MergeMatches --> LLMService
    LLMService --> LLM
```

---

## Tech Stack

| Layer    | Stack                                                                                                             |
| -------- | ----------------------------------------------------------------------------------------------------------------- |
| Backend  | FastAPI 2.x, SQLAlchemy 2, Celery (eager by default, no Redis required for dev), PostgreSQL                       |
| Frontend | React 19, TypeScript, Vite 7, MUI, Tailwind CSS, Recharts, React Router                                           |
| AI       | Ollama or OpenAI (LLM + embeddings), RAG via Elasticsearch dense vectors                                          |
| Run      | Docker Compose (Postgres + backend + frontend + Ollama + Elasticsearch; Keycloak opt-in via `--profile keycloak`) |

---

## Quick Start

### With Docker (recommended)

```bash
# From project root (--compatibility applies Ollama CPU/memory limits to fix cgroup parsing)
# Docker Desktop: allocate at least 6GB memory (Settings → Resources) for qwen2.5:7b
docker compose --compatibility up --build
```

- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API docs:** http://localhost:8000/api/v1/docs
- **Keycloak:** http://localhost:8080 (admin/admin)

Default DB: `postgresql://jobseeker:jobseeker@postgres:5432/jobseeker` (inside Compose).

**Keycloak (optional):** Auth is disabled by default. See [docs/KEYCLOAK_SETUP.md](docs/KEYCLOAK_SETUP.md). To enable: `KEYCLOAK_ENABLED=true docker compose --profile keycloak up`.

**LLM summary (optional):** After resume analysis, users can click "Generate AI summary" to get AI-generated career advice. The summary streams as the model generates it and is rendered as markdown with clickable job links. Requires Ollama or OpenAI configured. The `./scripts/test-and-build.sh` script pulls the Ollama model automatically. For manual `docker compose up`:

```bash
docker compose exec ollama ollama pull qwen2.5:7b
```

Default model is `qwen2.5:7b`. Use Settings → AI Config to switch to OpenAI or change models. Optional: create a custom model with the project Modelfile:

```bash
ollama create jobseeker-advisor -f Modelfile
# Then set LLM_MODEL=jobseeker-advisor in backend env or via AI Config
```

**RAG (vector search):** When `RAG_ENABLED=true` and Elasticsearch is running, resume analysis uses semantic search to find additional job matches. After importing jobs, run `POST /api/v1/jobs/sync-embeddings` (or use the streaming endpoint for progress). Pull the embedding model: `docker compose exec ollama ollama pull nomic-embed-text`.

**Resume recommendations:** After analysis, the app fetches hybrid search (RAG) job recommendations via `POST /api/v1/resume/recommendations`. Requires embeddings synced and RAG enabled.

### Production Deployment

Deploy to an Ubuntu server (e.g. home server) with one command:

```bash
./deploy/scripts/deploy.sh kkotlowski@hp-homeserver
```

The deploy script syncs the project via rsync, runs `docker compose up -d --build`, and ensures Ollama models (embedding + LLM) are pulled. See [deploy/README.md](deploy/README.md) for full documentation.

| Script | Purpose |
|--------|---------|
| `deploy/scripts/deploy.sh` | Sync + start stack on remote server |
| `deploy/scripts/test-and-deploy.sh` | Run tests locally, then deploy |
| `deploy/scripts/prepare-ubuntu-server.sh` | First-time server setup (Docker, UFW) |
| `deploy/scripts/migrate-db-to-server.sh` | Copy local DB to server |

Production stack: `deploy/docker-compose.prod.yml` (Postgres, Elasticsearch, Ollama, backend, frontend). `ollama-init` service pulls embedding and LLM models before the backend starts.

### Local Development

**Quick start (no Docker):** `./start.sh` runs backend + frontend. Requires Postgres running (e.g. `docker compose up postgres -d`).

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

### Test and Build Pipeline

```bash
./scripts/test-and-build.sh
```

Runs backend + frontend tests, then `docker compose up --build -d`, then pulls the Ollama model for resume summaries. See [docs/TESTING_PLAN.md](docs/TESTING_PLAN.md).

---

## Features

- **Job list** — Filter by status, saved, seniority, category, work type, location; pagination; duplicate grouping; alternate listings (same job on multiple sites).
- **Job detail** — View/edit job, mark saved, see detected skills and alternate URLs.
- **Bulk import** — Import from JustJoin.it and NoFluffJobs with resumable progress; start/cancel per source or all.
- **Analytics / dashboard** — Top skills, salary stats, charts (Recharts).
- **Skills** — Detected skills per job; summary and match endpoints.
- **Backup** — Download database as `.sql` (PostgreSQL `pg_dump`).
- **Resume analysis** — Upload PDF, extract skills, compare to positions with match score and bar charts. Optional LLM summary (Ollama or OpenAI) for AI-generated career advice. RAG (vector search via Elasticsearch) enriches matches with semantic retrieval. Hybrid job recommendations via `POST /resume/recommendations`.
- **AI configuration** — Switch between Ollama (local) and OpenAI; choose LLM and embedding models; ensure-model (pull Ollama model on demand); temperature and token limits. Inference metrics (latency, tokens) per model in Settings.
- **OpenAI support** — Use GPT-4o-mini or other models when API key is configured via Settings; embeddings from OpenAI or Ollama.
- **Streaming embedding sync** — Progress feedback when indexing jobs for RAG.
- **Keycloak auth** — Optional; app works without it. Login required for import, backup, and saving resume analyses when `KEYCLOAK_ENABLED=true`.
- **User & resume history** — Authenticated users get resume analyses persisted with extracted keywords.
- **Dark mode** — UI theme toggle.
- **API v1** — REST under `/api/v1/` with standardized error shape `{ error: { code, message, details? } }`.

---

## API Overview

| Area   | Base path        | Notes                                                                                                                                                       |
| ------ | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Jobs   | `/api/v1/jobs`   | CRUD, list with filters, parse URL, analytics, categories, seniorities, locations, top skills, duplicate check, recalculate salaries, sync-embeddings (RAG) |
| Skills | `/api/v1/skills` | Summary, detected, match                                                                                                                                    |
| Import | `/api/v1/import` | Status, start (all or per source), cancel                                                                                                                   |
| Backup | `/api/v1/backup` | POST create → download .sql                                                                                                                                 |
| Resume | `/api/v1/resume` | Analyze PDF, summarize, stream, history, **recommendations** (hybrid RAG)                                                                                   |
| AI     | `/api/v1/ai`     | Models (provider param), **ensure-model** (pull Ollama model), config, validate-key, metrics                                                                |
| Health | `/api/v1/health` | `{"status":"ok", "llm_available": bool, "database_available": bool, "elasticsearch_available": bool}`                                                       |

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

## Project Layout

```
job-seeker/
├── deploy/
│   ├── docker-compose.prod.yml   # Production stack (Postgres, ES, Ollama, backend, frontend)
│   ├── env.example.prod          # Production env template
│   ├── README.md                 # Deployment docs
│   └── scripts/
│       ├── deploy.sh             # Sync + docker compose on remote
│       ├── test-and-deploy.sh    # Test locally, then deploy
│       ├── prepare-ubuntu-server.sh
│       └── migrate-db-to-server.sh
├── backend/
│   ├── README.md
│   ├── app/
│   │   ├── main.py           # FastAPI app, CORS, routers
│   │   ├── database.py       # SQLAlchemy engine, session
│   │   ├── errors.py         # Standardized API error handlers
│   │   ├── celery_app.py     # Celery (eager by default)
│   │   ├── import_engine.py  # Bulk import state & recovery
│   │   ├── models/           # SQLAlchemy models, Pydantic schemas
│   │   ├── routers/          # jobs, skills, imports, backup, resume, ai_config
│   │   ├── parsers/          # JustJoin, NoFluffJobs scrapers
│   │   ├── services/         # currency, resume, llm, embedding, elasticsearch, ai_config, inference_log
│   │   └── migrations/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/
├── frontend/
│   ├── README.md
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api/              # client, types
│   │   ├── auth/             # AuthContext, useAuth
│   │   ├── components/       # SettingsModal, AIConfigContent, ImportContent, etc.
│   │   ├── contexts/         # ToastContext, useToast
│   │   └── pages/            # JobList, JobDetail, Import, Dashboard, Skills, Resume, etc.
│   ├── package.json
│   ├── vite.config.ts
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
├── Modelfile                  # Custom Ollama model for resume summaries
└── README.md
```

---

## Environment

Copy `.env.example` to `.env` and adjust. See `.env.example` for all variables.

| Variable                | Description                                                                                                                              |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`          | PostgreSQL URL (required for backend).                                                                                                   |
| `ENRICH_ON_IMPORT`      | When set (`1`, `true`, `yes`), NoFluffJobs import fetches each job page for description and nice-to-have skills. Slower but richer data. |
| `LLM_URL`               | Ollama API URL (e.g. `http://ollama:11434`). If unset, resume summaries use OpenAI when configured.                                      |
| `LLM_MODEL`             | Model name for summarization (default: `qwen2.5:7b`). Overridable via AI Config.                                                          |
| `LLM_TIMEOUT`           | Timeout in seconds for LLM requests (default: 30).                                                                                       |
| `LLM_SUMMARIZE_TIMEOUT` | Timeout for on-demand summarize (default: 90). Increase on small containers.                                                             |
| `LLM_MAX_OUTPUT_TOKENS` | Max tokens for summary output (default: 1024). Lower values help avoid 500 errors on small models or low-memory systems.                 |
| `ELASTICSEARCH_URL`     | Elasticsearch URL for RAG (default: `http://localhost:9200`).                                                                            |
| `EMBED_MODEL`           | Ollama embedding model (default: `nomic-embed-text`). Overridable via AI Config.                                                         |
| `EMBED_DIMS`            | Embedding dimensions (default: 768 for nomic-embed-text).                                                                                |
| `RAG_ENABLED`           | When `true`, resume analysis merges keyword + semantic matches.                                                                          |
| `CORS_ORIGINS`          | Comma-separated allowed origins (default: localhost dev URLs).                                                                           |
| `RATE_LIMIT`            | Global rate limit, e.g. `100/minute` (default: 100/minute).                                                                              |

**OpenAI API key:** Stored in DB via Settings → AI Config. Not in env; use the UI or `PUT /api/v1/ai/config`.

Celery runs in eager mode by default so imports work without Redis; optional Redis can be added for real background workers.
