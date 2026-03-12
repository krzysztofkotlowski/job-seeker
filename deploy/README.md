# Job Seeker Tracker — Production Deployment

Deploy the Job Seeker Tracker stack to an Ubuntu Server using Docker Compose, with `thin-llama` as the only self-hosted inference runtime.

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

### 2. Pin the `thin-llama` Git source

The deploy scripts now fetch `thin-llama` directly on the server from Git. Set these in `.env` before the first deploy:

```bash
THIN_LLAMA_GIT_URL=https://github.com/krzysztofkotlowski/thin-llama.git
THIN_LLAMA_GIT_REF=950969e1783d9f5e0cb802cc82552384de43c6be
```

Use a tag or commit SHA for `THIN_LLAMA_GIT_REF`. The deploy scripts clone the repo if missing, fetch tags, and check out that pinned ref in detached HEAD mode before building the runtime image.

### 3. Deploy the application

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

The script syncs the `job-seeker` repo via rsync, fetches `thin-llama` from the pinned Git ref on the server, and starts the stack. On first run, it creates `.env` from `deploy/env.example.prod` if missing. **Edit `.env` on the server** to set a strong `POSTGRES_PASSWORD` before the first deploy, or immediately after.

### 4. Access the app

Open `http://<server-ip>` in your browser. The frontend serves on port 80 and proxies `/api` to the backend.

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | PostgreSQL password | `jobseeker` |
| `LLM_MODEL` | Self-hosted chat model for resume summaries | `qwen2.5:7b` |
| `EMBED_MODEL` | Self-hosted embedding model for RAG | `bge-base-en:v1.5` |
| `EMBED_BULK_BATCH_SIZE` | Self-hosted embedding batch size during indexing | `16` |
| `LLM_MAX_OUTPUT_TOKENS` | Max tokens for AI output | `400` |
| `RAG_ENABLED` | Enable semantic search | `true` |
| `THIN_LLAMA_GIT_URL` | Git source for the self-hosted runtime | `https://github.com/krzysztofkotlowski/thin-llama.git` |
| `THIN_LLAMA_GIT_REF` | Pinned tag or commit to deploy | `fb1dfe4234a49e9da248635b8d5be1dabfe3be10` |
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

## thin-llama bootstrap

The stack no longer runs an Ollama container. Instead, `thin-llama` is the only self-hosted inference runtime.

The `thin-llama-init` one-shot service automatically:

1. waits for `thin-llama`
2. pulls the configured embedding and chat models
3. activates both models through `thin-llama`'s management API

The deploy scripts also run a post-deploy `thin-llama-init` step as a belt-and-suspenders bootstrap. **First deploy may take several minutes** while the GGUF models download.

To use different self-hosted models, set `LLM_MODEL` and `EMBED_MODEL` in `.env` before deploying. Those model names must exist in the `thin-llama` catalog available on the server.

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

# Re-run self-hosted model bootstrap
docker compose -f deploy/docker-compose.prod.yml run --rm thin-llama-init
```

## Hardware notes

The stack is tuned for a machine with ~16GB RAM and 6 CPUs (e.g. HP EliteDesk G4):

- Elasticsearch: 512MB heap
- `thin-llama`: small-model CPU inference for one chat model and one embedding model
- PostgreSQL, backend, frontend: default

Adjust `deploy/docker-compose.prod.yml` if your hardware differs. CPU limit must not exceed host CPUs (e.g. 6 on a 6-core machine).
