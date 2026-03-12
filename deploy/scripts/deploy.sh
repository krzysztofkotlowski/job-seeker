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
readonly DEFAULT_THIN_LLAMA_GIT_URL="https://github.com/krzysztofkotlowski/thin-llama.git"
readonly DEFAULT_THIN_LLAMA_GIT_REF="fb1dfe4234a49e9da248635b8d5be1dabfe3be10"

SERVER="${1:-${DEFAULT_SERVER}}"
REMOTE_PATH="${DEPLOY_PATH:-${DEFAULT_PATH}}"
REMOTE_THIN_LLAMA_PATH="${REMOTE_THIN_LLAMA_PATH:-$(dirname "${REMOTE_PATH}")/thin-llama}"
THIN_LLAMA_GIT_URL="${THIN_LLAMA_GIT_URL:-}"
THIN_LLAMA_GIT_REF="${THIN_LLAMA_GIT_REF:-}"
THIN_LLAMA_VERSION="${THIN_LLAMA_VERSION:-}"
THIN_LLAMA_BUILD_DATE="${THIN_LLAMA_BUILD_DATE:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

log() { echo "[deploy]" "$@"; }
log_err() { echo "[deploy] ERROR:" "$@" >&2; }

# --- Preflight ---
if [[ ! -f "${PROJECT_ROOT}/deploy/docker-compose.prod.yml" ]]; then
  log_err "docker-compose.prod.yml not found. Run from project root."
  exit 1
fi

log "Deploying to ${SERVER}:${REMOTE_PATH}"

log "Syncing job-seeker files..."
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

load_thin_llama_git_config() {
  local remote_values=""
  remote_values="$(ssh "${SERVER}" "if test -f '${REMOTE_PATH}/.env'; then set -a; . '${REMOTE_PATH}/.env'; printf '%s\n%s\n' \"\${THIN_LLAMA_GIT_URL:-}\" \"\${THIN_LLAMA_GIT_REF:-}\"; else printf '\n\n'; fi")"
  local remote_url=""
  local remote_ref=""
  remote_url="$(printf '%s' "${remote_values}" | sed -n '1p')"
  remote_ref="$(printf '%s' "${remote_values}" | sed -n '2p')"

  THIN_LLAMA_GIT_URL="${THIN_LLAMA_GIT_URL:-${remote_url}}"
  THIN_LLAMA_GIT_REF="${THIN_LLAMA_GIT_REF:-${remote_ref}}"
  if [[ -z "${THIN_LLAMA_GIT_URL}" ]]; then
    THIN_LLAMA_GIT_URL="${DEFAULT_THIN_LLAMA_GIT_URL}"
  fi
  if [[ -z "${THIN_LLAMA_GIT_REF}" ]]; then
    THIN_LLAMA_GIT_REF="${DEFAULT_THIN_LLAMA_GIT_REF}"
  fi
}

load_thin_llama_git_config

if [[ -z "${THIN_LLAMA_VERSION}" ]]; then
  THIN_LLAMA_VERSION="${THIN_LLAMA_GIT_REF:0:7}"
fi

log "Fetching thin-llama from Git..."
ssh "${SERVER}" "set -euo pipefail; mkdir -p '$(dirname "${REMOTE_THIN_LLAMA_PATH}")'; if [ ! -d '${REMOTE_THIN_LLAMA_PATH}/.git' ]; then git clone '${THIN_LLAMA_GIT_URL}' '${REMOTE_THIN_LLAMA_PATH}'; fi; cd '${REMOTE_THIN_LLAMA_PATH}'; git fetch --tags origin; git checkout --detach '${THIN_LLAMA_GIT_REF}'; git submodule update --init --recursive >/dev/null 2>&1 || true"

# --- Deploy on remote ---
log "Starting services on remote..."
ssh "${SERVER}" "cd ${REMOTE_PATH} && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f deploy/docker-compose.prod.yml up -d --build --remove-orphans"

# --- Ensure thin-llama models (belt-and-suspenders: thin-llama-init in the stack may have run already) ---
log "Ensuring thin-llama models (embedding + LLM)..."
ssh "${SERVER}" "cd ${REMOTE_PATH} && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f deploy/docker-compose.prod.yml run --rm thin-llama-init"

check_remote_backend_health_once() {
  if ssh "${SERVER}" "health=\$(curl -sf http://127.0.0.1/api/v1/health) && printf '%s' \"\${health}\" | grep -q '\"llm_available\":true'"; then
    return 0
  fi
  ssh "${SERVER}" \
    "cd '${REMOTE_PATH}' && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f deploy/docker-compose.prod.yml exec -T backend python -c \"import json, sys, urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=5)); sys.exit(0 if data.get('llm_available') else 1)\"" \
    >/dev/null 2>&1
}

verify_remote_health() {
  log "Verifying remote backend health..."
  for i in $(seq 1 60); do
    if check_remote_backend_health_once; then
      log "Remote backend health is OK."
      return 0
    fi
    if [[ "${i}" -eq 1 ]]; then
      log "Backend not ready yet; waiting..."
    fi
    sleep 3
  done

  log_err "Remote backend health check failed after retries."
  log "Diagnostics: docker compose ps"
  ssh "${SERVER}" "cd '${REMOTE_PATH}' && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f deploy/docker-compose.prod.yml ps" || true
  log "Diagnostics: backend logs (last 120 lines)"
  ssh "${SERVER}" "cd '${REMOTE_PATH}' && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f deploy/docker-compose.prod.yml logs --tail=120 backend" || true
  log "Diagnostics: thin-llama /health"
  ssh "${SERVER}" "cd '${REMOTE_PATH}' && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f deploy/docker-compose.prod.yml exec -T thin-llama curl -sS http://127.0.0.1:8080/health" || true
  log "Diagnostics: thin-llama /api/models"
  ssh "${SERVER}" "cd '${REMOTE_PATH}' && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f deploy/docker-compose.prod.yml exec -T thin-llama curl -sS http://127.0.0.1:8080/api/models" || true
  exit 1
}

verify_remote_health

log "Deployment complete."
log "App should be available at http://<server-ip>"
