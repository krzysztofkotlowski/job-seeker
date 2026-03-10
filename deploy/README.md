# Job Seeker Tracker — Production Deployment

Deploy the Job Seeker Tracker stack to an Ubuntu Server using Docker Compose.

## Prerequisites

- Ubuntu Server 22.04 or 24.04 LTS
- SSH access to the server
- Static IP configured on the server (or resolvable hostname)

## Quick Start

### 1. Prepare the server (first time only)

On your **workstation**, copy and run the preparation script on the server:

```bash
# From project root
scp deploy/scripts/prepare-ubuntu-server.sh kkotlowski@hp-homeserver:/tmp/
ssh kkotlowski@hp-homeserver 'sudo bash /tmp/prepare-ubuntu-server.sh'
```

This installs Docker, Docker Compose, Git, and configures UFW (SSH, HTTP, HTTPS).

### 2. Deploy the application

```bash
# From project root — test locally, then deploy
chmod +x deploy/scripts/test-and-deploy.sh
./deploy/scripts/test-and-deploy.sh kkotlowski@hp-homeserver
```

App-only deploy (recommended for frequent code updates; avoids unnecessary DB/search redeploy):

```bash
chmod +x deploy/scripts/test-and-deploy-app-only.sh
./deploy/scripts/test-and-deploy-app-only.sh kkotlowski@hp-homeserver
```

Skip local tests when needed:

```bash
RUN_TESTS=0 ./deploy/scripts/test-and-deploy-app-only.sh kkotlowski@hp-homeserver
```

Or deploy without running tests:

```bash
./deploy/scripts/deploy.sh kkotlowski@hp-homeserver
```

The script syncs the project via rsync and starts the stack. On first run, it creates `.env` from `deploy/env.example.prod` if missing. **Edit `.env` on the server** to set a strong `POSTGRES_PASSWORD` before the first deploy, or immediately after.

### 3. Access the app

Open `http://<server-ip>` in your browser. The frontend serves on port 80 and proxies `/api` to the backend.

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | PostgreSQL password | `jobseeker` |
| `LLM_MODEL` | Ollama model for resume summaries | `qwen2.5:7b` |
| `EMBED_MODEL` | Ollama embedding model for RAG | `all-minilm` |
| `LLM_MAX_OUTPUT_TOKENS` | Max tokens for AI output | `400` |
| `RAG_ENABLED` | Enable semantic search | `true` |
| `KEYCLOAK_ENABLED` | Enable Keycloak auth | `false` |
| `CORS_ORIGINS` | Allowed origins (`*` for same-origin) | `*` |

Copy `deploy/env.example.prod` to `.env` on the server and adjust as needed.

## Environment variables

- `DEPLOY_SERVER` — Override default server (e.g. `kkotlowski@hp-homeserver`)
- `DEPLOY_PATH` — Remote app directory (default: `/opt/jobseeker`)

Example:

```bash
DEPLOY_PATH=/home/kkotlowski/jobseeker ./deploy/scripts/deploy.sh
```

## Database migration (local → server)

To copy your local database to the server:

```bash
# Ensure local postgres is running
docker compose up postgres -d

# Run migration
./deploy/scripts/migrate-db-to-server.sh kkotlowski@hp-homeserver
```

The script dumps the local DB, copies it to the server, restores it, and cleans up.

## Ollama models

The `ollama-init` service automatically pulls the embedding model (`all-minilm`) and LLM model (`qwen2.5:7b`) before the backend starts. The deploy script also runs a post-deploy step to ensure models are pulled. **First deploy may take several minutes** while models download.

To use different models, set `LLM_MODEL` and `EMBED_MODEL` in `.env` before deploying.

**If embedding still fails (404 on /api/embed):** Manually pull the models on the server:

```bash
ssh kkotlowski@hp-homeserver
cd /opt/jobseeker
docker compose -f deploy/docker-compose.prod.yml exec ollama ollama pull all-minilm
docker compose -f deploy/docker-compose.prod.yml exec ollama ollama pull qwen2.5:7b
```

## Manual operations

```bash
# SSH to server
ssh kkotlowski@hp-homeserver
cd /opt/jobseeker

# Start
docker compose -f deploy/docker-compose.prod.yml up -d

# Stop
docker compose -f deploy/docker-compose.prod.yml down

# View logs
docker compose -f deploy/docker-compose.prod.yml logs -f

# Rebuild after code changes
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

## Hardware notes

The stack is tuned for a machine with ~16GB RAM and 6 CPUs (e.g. HP EliteDesk G4):

- Elasticsearch: 512MB heap
- Ollama: 6 CPUs, 10GB limit (uses all cores for faster inference)
- PostgreSQL, backend, frontend: default

Adjust `deploy/docker-compose.prod.yml` if your hardware differs. CPU limit must not exceed host CPUs (e.g. 6 on a 6-core machine).
