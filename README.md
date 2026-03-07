# Job Seeker Tracker

> Full-stack job tracker: scrape JustJoin.it & NoFluffJobs, store in PostgreSQL, analyze with Elasticsearch RAG + Ollama embeddings. React 19 + FastAPI. Resume PDF analysis with keyword/semantic matching, AI summaries, optional Keycloak auth. Docker Compose, Celery, rate limiting.

---

## Architecture Overview

### Container Topology

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
    Backend -->|"LLM + embeddings"| Ollama
    Browser -.->|"OAuth"| Keycloak
    Backend -.->|"JWT validate"| Keycloak
```

### API Request Flow

```mermaid
flowchart LR
    subgraph frontend [Frontend]
        React[React 19]
        APIClient[API Client]
        AuthCtx[AuthContext]
    end

    subgraph backend [Backend]
        FastAPI[FastAPI]
        Routers[Routers]
        Services[Services]
    end

    subgraph data [Data Layer]
        DB[(PostgreSQL)]
        ES[(Elasticsearch)]
        LLM[Ollama]
    end

    React --> AuthCtx
    React --> APIClient
    APIClient -->|"Bearer token"| FastAPI
    FastAPI --> Routers
    Routers --> Services
    Services --> DB
    Services --> ES
    Services --> LLM
```

### Import Pipeline

```mermaid
flowchart TB
    subgraph user [User]
        StartImport[POST /import/start]
    end

    subgraph backend [Backend]
        ImportRouter[Import Router]
        Celery[Celery Task]
        ImportEngine[Import Engine]
        subgraph parsers [Parsers]
            JJ[JustJoin Parser]
            NFJ[NoFluffJobs Parser]
        end
        SkillDetector[Skill Detector]
        Currency[Currency Service]
    end

    subgraph external [External]
        JJSite[justjoin.it]
        NFJSite[nofluffjobs.com]
    end

    subgraph storage [Storage]
        Postgres[(PostgreSQL)]
    end

    StartImport --> ImportRouter
    ImportRouter --> Celery
    Celery --> ImportEngine
    ImportEngine -->|"per source"| JJ
    ImportEngine -->|"per source"| NFJ
    JJ -->|"HTTP scrape"| JJSite
    NFJ -->|"HTTP scrape"| NFJSite
    ImportEngine -->|"insert JobRow"| Postgres
    ImportEngine --> Currency
    ImportEngine --> SkillDetector
    SkillDetector -->|"read/write"| Postgres
```

### Resume Analysis Flow

```mermaid
flowchart TB
    subgraph user [User]
        UploadPDF[Upload PDF]
    end

    subgraph backend [Backend]
        ResumeRouter[Resume Router]
        ResumeKeywords[Resume Keywords\nPyPDF extract]
        ResumeService[Resume Service]
        MatchJobs[match_jobs_to_skills]
        BuildCategory[build_by_category]
        RAGCheck{RAG enabled?}
        EmbedService[Embedding Service]
        ESService[Elasticsearch Service]
        MergeMatches[merge_keyword_and_semantic]
        LLMService[LLM Service]
    end

    subgraph data [Data Layer]
        Postgres[(PostgreSQL)]
        ES[(Elasticsearch)]
        Ollama[Ollama]
    end

    UploadPDF --> ResumeRouter
    ResumeRouter --> ResumeKeywords
    ResumeKeywords -->|"keywords"| ResumeService
    ResumeService --> MatchJobs
    ResumeService --> BuildCategory
    MatchJobs -->|"read jobs"| Postgres
    BuildCategory -->|"read jobs"| Postgres
    ResumeService --> RAGCheck
    RAGCheck -->|"yes"| EmbedService
    EmbedService -->|"embed skills"| Ollama
    EmbedService -->|"vector"| ESService
    ESService -->|"kNN search"| ES
    ESService -->|"semantic matches"| MergeMatches
    MergeMatches -->|"keyword matches"| MatchJobs
    RAGCheck -->|"no"| MergeMatches
    MergeMatches -->|"matches"| LLMService
    LLMService -->|"summarize"| Ollama
```

### Embedding Sync Flow

```mermaid
flowchart TB
    subgraph trigger [Trigger]
        SyncAPI[POST /jobs/sync-embeddings]
        Startup[Backend startup]
    end

    subgraph backend [Backend]
        JobsRouter[Jobs Router]
        ESClient[ES Service]
        EmbedClient[Embedding Service]
    end

    subgraph data [Data Layer]
        Postgres[(PostgreSQL)]
        Ollama[Ollama]
        Elasticsearch[(Elasticsearch)]
    end

    SyncAPI --> JobsRouter
    Startup -->|"background thread"| JobsRouter
    JobsRouter -->|"fetch JobRow"| Postgres
    JobsRouter --> EmbedClient
    EmbedClient -->|"embed_batch\njob text"| Ollama
    EmbedClient -->|"vectors"| ESClient
    ESClient -->|"bulk index"| Elasticsearch
```

### Resume RAG Merge Logic

```mermaid
flowchart LR
    subgraph inputs [Inputs]
        Keyword[Keyword matches\nDB query]
        Semantic[Semantic matches\nES kNN]
    end

    subgraph merge [Merge]
        Dedup[deduplicate by job_id]
        Sort[sort by score]
        Limit[max_total=8]
    end

    subgraph output [Output]
        Matches[Matches to user]
    end

    Keyword --> Dedup
    Semantic --> Dedup
    Dedup --> Sort
    Sort --> Limit
    Limit --> Matches
```

---

## Features

- **Job list** — Filter by status, saved, seniority, category, work type, location; pagination; duplicate grouping; alternate listings (same job on multiple sites).
- **Job detail** — View/edit job, mark saved, see detected skills and alternate URLs.
- **Bulk import** — Import from JustJoin.it and NoFluffJobs with resumable progress; start/cancel per source or all.
- **Analytics / dashboard** — Top skills, salary stats, charts (Recharts).
- **Skills** — Detected skills per job; summary and match endpoints.
- **Backup** — Download database as `.sql` (PostgreSQL `pg_dump`).
- **Resume analysis** — Upload PDF, extract skills, compare to positions with match score and bar charts. Optional LLM summary (Ollama) for AI-generated career advice. RAG (vector search via Elasticsearch) enriches matches with semantic retrieval when enabled.
- **Keycloak auth** — Optional; app works without it. Login required for import, backup, and saving resume analyses when `KEYCLOAK_ENABLED=true`.
- **User & resume history** — Authenticated users get resume analyses persisted with extracted keywords.
- **Dark mode** — UI theme toggle.
- **API v1** — REST under `/api/v1/` with standardized error shape `{ error: { code, message, details? } }`.

---

## Tech Stack

| Layer    | Stack                                                                                                             |
| -------- | ----------------------------------------------------------------------------------------------------------------- |
| Backend  | FastAPI 2.x, SQLAlchemy 2, Celery (eager by default, no Redis required for dev), PostgreSQL                       |
| Frontend | React 19, TypeScript, Vite 7, MUI, Tailwind CSS, Recharts, React Router                                           |
| AI       | Ollama (LLM + embeddings), RAG via Elasticsearch dense vectors                                                    |
| Run      | Docker Compose (Postgres + backend + frontend + Ollama + Elasticsearch; Keycloak opt-in via `--profile keycloak`) |

---

## Quick Start

### With Docker (recommended)

**Prerequisites:** Docker Desktop with 6GB memory (Settings → Resources → Memory). phi3:mini runs smoothly at 6GB.

```bash
# From project root (--compatibility applies Ollama CPU/memory limits to fix cgroup parsing)
docker compose --compatibility up --build
```

- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API docs:** http://localhost:8000/api/v1/docs
- **Keycloak:** http://localhost:8080 (admin/admin)

Default DB: `postgresql://jobseeker:jobseeker@postgres:5432/jobseeker` (inside Compose).

**Keycloak (optional):** Auth is disabled by default. See [docs/KEYCLOAK_SETUP.md](docs/KEYCLOAK_SETUP.md). To enable: `KEYCLOAK_ENABLED=true docker compose --profile keycloak up`.

**LLM summary (optional):** After resume analysis, users can click "Generate AI summary" to get AI-generated career advice. The summary streams as the model generates it and is rendered as markdown with clickable job links. Requires Ollama running with a model. The `./scripts/test-and-build.sh` script pulls the model automatically. For manual `docker compose up`, run:

```bash
docker compose exec ollama ollama pull phi3:mini
```

Default model is `phi3:mini`. For different quality: `llama3.2:1b`, `llama3.2:3b`, or `qwen3.5:0.8b`. Set `LLM_MODEL` in backend env if needed. Optional: create a custom model with the project Modelfile for improved prompt adherence:

```bash
ollama create jobseeker-advisor -f Modelfile
# Then set LLM_MODEL=jobseeker-advisor in backend env
```

**RAG (vector search):** When `RAG_ENABLED=true` and Elasticsearch is running, resume analysis uses semantic search to find additional job matches. After importing jobs, run `POST /api/v1/jobs/sync-embeddings` to index jobs for RAG. Pull the embedding model: `docker compose exec ollama ollama pull nomic-embed-text`.

**LLM 500 error troubleshooting:** If you see "AI summary unavailable" with a 500 from Ollama: (1) Ensure the model is pulled: `docker compose exec ollama ollama pull phi3:mini`. (2) Test locally: `docker compose exec ollama ollama run phi3:mini "Hello"`. (3) Reduce `LLM_MAX_OUTPUT_TOKENS` to 512 if still failing. (4) Check backend logs for the full Ollama error response. (5) Update Ollama: `docker compose pull ollama` and restart. (6) **Cgroup "max" parsing bug:** If Ollama logs show `failed to parse CPU allowed micro secs` with `parsing "max": invalid syntax`, the container's cgroup reports unlimited CPU and Ollama fails to parse it. The project's `docker-compose.yml` sets `deploy.resources.limits` (cpus, memory) and `OLLAMA_NUM_THREAD` to work around this. Run with `docker compose --compatibility up` so these limits are applied (plain `docker compose up` ignores `deploy` outside Swarm). If using a custom compose, add explicit CPU limits (e.g. `cpus: "4"`) to the Ollama service. (7) **"signal: killed" / OOM:** If `ollama run phi3:mini` fails with "llama runner process has terminated: signal: killed", the container ran out of memory. Set Docker Desktop memory (Settings → Resources → Memory) to 6GB minimum; 6GB runs phi3:mini smoothly. For headroom, use 8GB. Low-memory fallback: `LLM_MODEL=llama3.2:1b` (set in backend env, then `ollama pull llama3.2:1b`).

### Local Development

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

## API Overview

| Area   | Base path        | Notes                                                                                                                                                       |
| ------ | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Jobs   | `/api/v1/jobs`   | CRUD, list with filters, parse URL, analytics, categories, seniorities, locations, top skills, duplicate check, recalculate salaries, sync-embeddings (RAG) |
| Skills | `/api/v1/skills` | Summary, detected, match                                                                                                                                    |
| Import | `/api/v1/import` | Status, start (all or per source), cancel                                                                                                                   |
| Backup | `/api/v1/backup` | POST create → download .sql                                                                                                                                 |
| Resume | `/api/v1/resume` | Analyze PDF, summarize, stream, history                                                                                                                     |
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
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app, CORS, routers
│   │   ├── database.py       # SQLAlchemy engine, session
│   │   ├── errors.py         # Standardized API error handlers
│   │   ├── celery_app.py     # Celery (eager by default)
│   │   ├── import_engine.py  # Bulk import state & recovery
│   │   ├── models/           # SQLAlchemy models, Pydantic schemas
│   │   ├── routers/          # jobs, skills, imports, backup, resume
│   │   ├── parsers/          # JustJoin, NoFluffJobs scrapers
│   │   ├── services/         # currency, resume, llm, embedding, elasticsearch
│   │   └── migrations/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api/              # client, types
│   │   ├── auth/             # AuthContext, useAuth
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
| `LLM_URL`               | Ollama API URL (e.g. `http://ollama:11434`). If unset, resume summaries are disabled.                                                    |
| `LLM_MODEL`             | Model name for summarization (default: `phi3:mini`). Use `llama3.2:1b`, `qwen3.5:0.8b`, or `llama3.2:3b` for different quality.         |
| `LLM_TIMEOUT`           | Timeout in seconds for LLM requests (default: 30).                                                                                       |
| `LLM_SUMMARIZE_TIMEOUT` | Timeout for on-demand summarize (default: 90). Increase on small containers.                                                             |
| `LLM_MAX_OUTPUT_TOKENS` | Max tokens for summary output (default: 1024). Lower values help avoid 500 errors on small models or low-memory systems.                  |
| `ELASTICSEARCH_URL`     | Elasticsearch URL for RAG (default: `http://localhost:9200`).                                                                            |
| `EMBED_MODEL`           | Ollama embedding model (default: `nomic-embed-text`). Run `ollama pull nomic-embed-text`.                                                |
| `EMBED_DIMS`            | Embedding dimensions (default: 768 for nomic-embed-text).                                                                                |
| `RAG_ENABLED`           | When `true`, resume analysis merges keyword + semantic matches.                                                                          |
| `CORS_ORIGINS`          | Comma-separated allowed origins (default: localhost dev URLs).                                                                           |
| `RATE_LIMIT`            | Global rate limit, e.g. `100/minute` (default: 100/minute).                                                                              |

**API versioning:** v1 is under `/api/v1/`. For v2, we would add `/api/v2/` and document deprecation of v1 with a timeline.

Celery runs in eager mode by default so imports work without Redis; optional Redis can be added for real background workers.
