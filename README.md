# Job Seeker Tracker

AI job-intelligence platform for sourcing jobs, indexing them for semantic retrieval, analyzing resumes, and generating actionable career guidance.

This project combines a React frontend, FastAPI backend, PostgreSQL, Elasticsearch, Redis, Celery, and Ollama/OpenAI into one end-to-end system. It ingests real job data from Polish IT job boards, normalizes and deduplicates listings, builds a managed vector index for recommendations, and lets a user move from raw job aggregation to AI-assisted resume analysis inside one product.

From a portfolio perspective, this is not a UI-only app or an isolated AI demo. It shows full ownership of product delivery across ingestion, async pipelines, search infrastructure, AI integration, production deployment, and frontend UX.

## What This Demonstrates

- AI-assisted resume analysis with local or hosted model providers
- Hybrid retrieval using keyword matching plus Elasticsearch dense-vector search
- Persistent background indexing and scraping workflows with Redis + Celery
- Active vector-index management for stable recommendations after model changes
- Full-stack product ownership: frontend, backend, data model, infrastructure, CI, and deployment
- Self-hosted production deployment with Docker Compose on Ubuntu Server

## Key Capabilities

- Aggregate jobs from JustJoin.it and NoFluffJobs into a unified dataset
- Filter, group duplicates, inspect details, and track application state
- Upload a PDF resume and extract skills matched against imported jobs
- Generate hybrid recommendations from the active semantic index
- Produce AI summaries and career guidance with Ollama or OpenAI
- Configure LLM and embedding providers from the UI
- Run persistent embedding sync with tracked progress and active-index cutover
- Explore skills, salary trends, and dashboard analytics
- Enable optional Keycloak auth for protected operations

## Architecture Overview

```mermaid
flowchart TB
    Browser["React 19 Frontend"]
    API["FastAPI API"]
    Worker["Celery Worker"]
    Redis["Redis"]
    Postgres["PostgreSQL"]
    ES["Elasticsearch"]
    AI["Ollama / OpenAI"]
    Sources["JustJoin.it / NoFluffJobs"]

    Browser -->|"HTTP /api"| API
    API --> Postgres
    API --> ES
    API --> AI
    API --> Redis
    Worker --> Redis
    Worker --> Postgres
    Worker --> ES
    Worker --> AI
    API -->|"import jobs"| Sources
```

### Core design

- `FastAPI` owns the REST API, resume analysis flow, AI configuration, and health/operational endpoints.
- `PostgreSQL` stores the canonical job and application data.
- `Elasticsearch` stores the active dense-vector recommendation index and powers semantic retrieval.
- `Redis + Celery` run background import and embedding-sync work outside the request path.
- `Ollama` provides local LLM and embedding inference by default; `OpenAI` can be used from the same UI configuration layer.
- The frontend is a single-page React app focused on job exploration, resume analysis, import operations, and AI settings.

### Recommendation / RAG flow

```mermaid
flowchart LR
    Resume["PDF Resume"]
    Extract["Skill Extraction"]
    Status["Active Index Status"]
    Embed["Query Embedding"]
    KNN["Elasticsearch kNN"]
    Merge["Keyword + Semantic Merge"]
    Summary["AI Summary / Guidance"]

    Resume --> Extract
    Extract --> Merge
    Extract --> Status
    Status --> Embed
    Embed --> KNN
    KNN --> Merge
    Merge --> Summary
```

The recommendation pipeline uses the currently activated embedding run rather than guessing index shape from config. That keeps semantic search stable when embedding models or dimensions change and makes full rebuilds explicit.

## Tech Stack

| Layer    | Stack                                                         |
| -------- | ------------------------------------------------------------- |
| Frontend | React 19, TypeScript, Vite 7, MUI 7, React Router 7, Recharts |
| Backend  | FastAPI, SQLAlchemy 2, Pydantic 2, PyPDF, SlowAPI             |
| Data     | PostgreSQL 16, Elasticsearch 8                                |
| Async    | Celery 5, Redis 7                                             |
| AI       | Ollama, OpenAI, local embeddings via `all-minilm` by default  |
| Infra    | Docker Compose, Nginx frontend container, GitHub Actions CI   |

## Local Quick Start

### Docker Compose

```bash
docker compose --compatibility up --build
```

App endpoints:

- Frontend: [http://localhost:5173](http://localhost:5173)
- Backend API: [http://localhost:8000](http://localhost:8000)
- OpenAPI docs: [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)

The local stack includes:

- `postgres`
- `redis`
- `elasticsearch`
- `ollama`
- `backend`
- `worker`
- `frontend`

Optional auth:

```bash
KEYCLOAK_ENABLED=true docker compose --profile keycloak up
```

### Local development without the full stack

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://jobseeker:jobseeker@localhost:5432/jobseeker
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend proxies `/api` to the backend through Vite during development.

## AI / RAG Workflow

### Default local AI setup

- Summary model: `qwen2.5:7b`
- Embedding model: `all-minilm`
- Vector dimensions: `384`

Pull models manually if needed:

```bash
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull all-minilm
```

### Resume analysis path

1. Import jobs from supported sources
2. Run embedding sync to build the active semantic index
3. Upload a PDF resume
4. Extract skills and keyword matches
5. Query the active vector index for semantic recommendations
6. Generate an AI summary from the matched job context

### Important implementation details

- Embedding sync is tracked persistently, not only in browser state
- The app distinguishes between the latest completed run and the active recommendation index
- Incremental indexing is allowed only when embedding settings match the active index
- Recommendations continue to use the active run metadata until a full rebuild activates a new index

## Deployment

Production deployment is documented in [deploy/README.md](deploy/README.md).

Common paths:

```bash
./deploy/scripts/deploy.sh <user>@<server>
./deploy/scripts/test-and-deploy-app-only.sh <user>@<server>
```

The production stack uses [deploy/docker-compose.prod.yml](deploy/docker-compose.prod.yml) and includes:

- PostgreSQL
- Redis
- Elasticsearch
- Ollama
- `ollama-init` model bootstrap
- FastAPI backend
- Celery worker
- Frontend served on port `80`

Use the root README for product and setup orientation. Use the deploy README for server preparation, env configuration, and operational commands.

## Testing and CI

### Local test commands

Backend:

```bash
cd backend
pytest
```

Frontend:

```bash
cd frontend
npm test -- --run
npm run lint
npm run build
```

Convenience pipeline:

```bash
./scripts/test-and-build.sh
```

### CI

GitHub Actions runs:

- backend lint with Ruff
- backend tests with PostgreSQL service
- frontend lint
- frontend tests
- frontend production build

See [.github/workflows/ci.yml](.github/workflows/ci.yml).

## Project Structure

```text
job-seeker/
├── backend/
│   ├── app/
│   │   ├── routers/       # jobs, resume, imports, skills, ai_config, backup
│   │   ├── services/      # resume, embeddings, elasticsearch, AI config, indexing
│   │   ├── parsers/       # source-specific job parsers
│   │   ├── models/        # DB tables and schemas
│   │   ├── migrations/    # lightweight migration layer
│   │   ├── main.py        # FastAPI entrypoint
│   │   └── celery_app.py  # worker entrypoint
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── pages/         # dashboard, jobs, resume, skills
│   │   ├── components/    # import, AI config, shared UI
│   │   └── api/           # typed client + API models
├── deploy/
│   ├── docker-compose.prod.yml
│   ├── scripts/
│   └── README.md
├── docs/
│   ├── KEYCLOAK_SETUP.md
│   ├── TESTING_PLAN.md
│   └── ADR/
├── docker-compose.yml
└── scripts/
```

## Notes on Tradeoffs

- Ollama-first defaults make the project self-hostable and cheap to run, but model quality and latency depend on local hardware.
- Elasticsearch vector search keeps retrieval infrastructure explicit and inspectable, at the cost of managing index lifecycle and rebuilds.
- Celery + Redis add operational complexity, but they keep imports and embedding sync out of the request path and make long-running jobs reliable.
- The product is currently specialized around Polish IT sources, but the ingestion architecture is adapter-based rather than hard-coded to one board.

## Roadmap

- Add more job source adapters with the same normalization pipeline
- Extend resume history and user-specific recommendation persistence
- Improve observability around import and embedding-job throughput
- Add richer ranking explanations for recommendation results
