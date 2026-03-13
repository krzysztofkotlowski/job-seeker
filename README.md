# Job Seeker Tracker

AI job-intelligence platform for sourcing jobs, indexing them for semantic retrieval, analyzing resumes, and generating actionable career guidance.

**Related project:** [thin-llama](https://github.com/krzysztofkotlowski/thin-llama) — self-hosted llama.cpp runtime with an Ollama-compatible API, used by this app for local chat and embeddings.

[![thin-llama](https://img.shields.io/badge/thin--llama-Go%20wrapper%20for%20llama.cpp-blue?style=flat-square&logo=github)](https://github.com/krzysztofkotlowski/thin-llama)

---

## Architecture

### System overview

```mermaid
flowchart TB
    Browser["React 19 Frontend"]
    API["FastAPI API"]
    Worker["Celery Worker"]
    Redis["Redis"]
    Postgres["PostgreSQL"]
    ES["Elasticsearch"]
    AI["thin-llama / OpenAI"]
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

### RAG / recommendation flow

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

### thin-llama integration

`thin-llama` acts as the AI runtime for both chat (resume summaries, career guidance) and embeddings (RAG). It exposes an Ollama-compatible API, so the backend uses the same client for local and hosted providers. Production deployment fetches `thin-llama` from a pinned Git ref on the server.

---

## Project Description

Job Seeker Tracker combines a React frontend, FastAPI backend, PostgreSQL, Elasticsearch, Redis, Celery, and a self-hosted/OpenAI model layer into one end-to-end system. It ingests real job data from Polish IT job boards, normalizes and deduplicates listings, builds a managed vector index for recommendations, and lets a user move from raw job aggregation to AI-assisted resume analysis inside one product.

<p align="center">
  <img src="assets/job-seeker-jobs-view.png" alt="Jobs list" width="100%" />
</p>

The dashboard gives an overview of the indexed dataset and import status:

<p align="center">
  <img src="assets/job-seeker-dashboard.gif" alt="Dashboard" width="100%" />
</p>
<p align="center"><sub><a href="assets/job-seeker-dashboard.mp4">Full quality: mp4</a></sub></p>

From a portfolio perspective, this is not a UI-only app or an isolated AI demo. It shows full ownership of product delivery across ingestion, async pipelines, search infrastructure, AI integration, production deployment, and frontend UX.

## Tech Stack

| Layer    | Stack                                                         |
| -------- | ------------------------------------------------------------- |
| Frontend | React 19, TypeScript, Vite 7, MUI 7, React Router 7, Recharts |
| Backend  | FastAPI, SQLAlchemy 2, Pydantic 2, PyPDF, SlowAPI              |
| Data     | PostgreSQL 16, Elasticsearch 8                                |
| Async    | Celery 5, Redis 7                                             |
| AI       | thin-llama, OpenAI, local embeddings via `nomic-embed-text` by default |
| Infra    | Docker Compose, Nginx frontend container, GitHub Actions CI   |

## Key Capabilities

- Aggregate jobs from JustJoin.it and NoFluffJobs into a unified dataset
- Filter, group duplicates, inspect details, and track application state
- Upload a PDF resume and extract skills matched against imported jobs — the app embeds your skills and runs hybrid search (keyword + semantic) over the indexed jobs:

<p align="center">
  <img src="assets/job-seeker-resume-view.gif" alt="Resume analysis" width="100%" />
</p>
<p align="center"><sub><a href="assets/job-seeker-resume-view.mp4">Full quality: mp4</a></sub></p>

- Generate hybrid recommendations from the active semantic index
- Produce AI summaries and career guidance with thin-llama or OpenAI
- Configure LLM and embedding providers from the UI:

<p align="center">
  <img src="assets/job-seeker-settings.gif" alt="AI settings" width="100%" />
</p>
<p align="center"><sub><a href="assets/job-seeker-settings.mp4">Full quality: mp4</a></sub></p>

- Run persistent embedding sync with tracked progress and active-index cutover
- Explore skills, salary trends, and dashboard analytics:

<p align="center">
  <img src="assets/job-seeker-skills-view.png" alt="Skills view" width="100%" />
</p>

- Enable optional Keycloak auth for protected operations

---

## Quick Start

### Docker Compose

```bash
docker compose --compatibility up --build
```

App endpoints:

- Frontend: [http://localhost:5173](http://localhost:5173)
- Backend API: [http://localhost:8000](http://localhost:8000)
- OpenAPI docs: [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)

The local stack includes: postgres, redis, elasticsearch, thin-llama, thin-llama-init, backend, worker, frontend.

Bootstrap the self-hosted runtime manually if needed:

```bash
docker compose run --rm thin-llama-init
```

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

---

## Deployment

Production deployment is documented in [deploy/README.md](deploy/README.md).

The production stack uses [deploy/docker-compose.prod.yml](deploy/docker-compose.prod.yml) and includes thin-llama (fetched from Git on the server), thin-llama-init model bootstrap, PostgreSQL, Redis, Elasticsearch, FastAPI backend, Celery worker, and frontend on port 80.

```bash
./deploy/scripts/deploy.sh <user>@<server>
./deploy/scripts/test-and-deploy-app-only.sh <user>@<server>
```

---

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
├── assets/
│   ├── *.png              # screenshots
│   ├── *.gif              # demo GIFs (run ./assets/convert-videos.sh to generate from .mov)
│   └── convert-videos.sh  # ffmpeg script: .mov → .mp4 + .gif
├── docs/
│   ├── KEYCLOAK_SETUP.md
│   ├── TESTING_PLAN.md
│   └── ADR/
├── docker-compose.yml
└── scripts/
```

---

## Notes on Tradeoffs

- **thin-llama vs Ollama:** thin-llama is a minimal Go-based control plane for llama.cpp; Ollama offers more features but adds complexity. thin-llama keeps the stack self-hostable and lightweight.
- **Self-hosted vs OpenAI:** thin-llama-first defaults make the project cheap to run, but model quality and latency depend on local hardware. OpenAI can be configured from the same UI for higher quality when needed.
- **Elasticsearch vector search** keeps retrieval infrastructure explicit and inspectable, at the cost of managing index lifecycle and rebuilds.
- **Celery + Redis** add operational complexity, but keep imports and embedding sync out of the request path and make long-running jobs reliable.
- The product is currently specialized around Polish IT sources, but the ingestion architecture is adapter-based rather than hard-coded to one board.

---

## Testing and CI

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

GitHub Actions runs backend lint/tests, frontend lint/tests, and production build. See [.github/workflows/ci.yml](.github/workflows/ci.yml).
