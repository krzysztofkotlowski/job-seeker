#!/usr/bin/env bash
# Deploy Job Seeker Tracker to production server
#
# Pushes the project via rsync and starts Docker Compose on the remote host.
# Requires: SSH access (key-based auth recommended), Docker on the server.
#
# Usage:
#   ./deploy/scripts/deploy.sh [SERVER]
#
# Examples:
#   ./deploy/scripts/deploy.sh
#   ./deploy/scripts/deploy.sh kkotlowski@hp-homeserver
#
# Environment:
#   DEPLOY_SERVER  - Override default server (default: kkotlowski@hp-homeserver)
#   DEPLOY_PATH   - Remote path (default: /opt/jobseeker)

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly DEFAULT_SERVER="${DEPLOY_SERVER:-kkotlowski@hp-homeserver}"
readonly DEFAULT_PATH="${DEPLOY_PATH:-/opt/jobseeker}"

SERVER="${1:-${DEFAULT_SERVER}}"
REMOTE_PATH="${DEPLOY_PATH:-${DEFAULT_PATH}}"

log() { echo "[deploy]" "$@"; }
log_err() { echo "[deploy] ERROR:" "$@" >&2; }

# --- Preflight ---
if [[ ! -f "${PROJECT_ROOT}/deploy/docker-compose.prod.yml" ]]; then
  log_err "docker-compose.prod.yml not found. Run from project root."
  exit 1
fi

log "Deploying to ${SERVER}:${REMOTE_PATH}"

# --- Sync files ---
log "Syncing project files..."
rsync -avz --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude '__pycache__' \
  --exclude 'pgdata' \
  --exclude '*.pyc' \
  --exclude '.coverage' \
  --exclude 'dist' \
  --exclude '.env' \
  "${PROJECT_ROOT}/" "${SERVER}:${REMOTE_PATH}/"

# --- Ensure .env exists on remote ---
if ! ssh "${SERVER}" "test -f ${REMOTE_PATH}/.env"; then
  log "Creating .env from env.example.prod on remote..."
  ssh "${SERVER}" "cp ${REMOTE_PATH}/deploy/env.example.prod ${REMOTE_PATH}/.env"
  log "Edit ${REMOTE_PATH}/.env on the server and set POSTGRES_PASSWORD before first run."
fi

# --- Deploy on remote ---
log "Starting services on remote..."
ssh "${SERVER}" "cd ${REMOTE_PATH} && docker compose -f deploy/docker-compose.prod.yml up -d --build"

# --- Ensure Ollama models (belt-and-suspenders: ollama-init may have failed) ---
log "Ensuring Ollama models (embedding + LLM)..."
for i in $(seq 1 30); do
  if ssh "${SERVER}" "cd ${REMOTE_PATH} && docker compose -f deploy/docker-compose.prod.yml exec -T ollama ollama pull all-minilm" 2>/dev/null; then
    log "Embedding model (all-minilm) ready."
    break
  fi
  log "Waiting for Ollama (attempt ${i}/30)..."
  sleep 5
done
for i in $(seq 1 10); do
  if ssh "${SERVER}" "cd ${REMOTE_PATH} && docker compose -f deploy/docker-compose.prod.yml exec -T ollama ollama pull qwen2.5:7b" 2>/dev/null; then
    log "LLM model (qwen2.5:7b) ready."
    break
  fi
  sleep 5
done

log "Deployment complete."
log "App should be available at http://<server-ip>"
