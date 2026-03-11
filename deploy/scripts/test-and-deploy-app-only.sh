#!/usr/bin/env bash
# Test locally, then deploy only application services on remote.
#
# Goal: avoid unnecessary PostgreSQL/Elasticsearch redeployments.
# - Existing DB/search/broker containers are only started (not recreated).
# - Only backend/frontend/worker are rebuilt/redeployed.
#
# Usage:
#   ./deploy/scripts/test-and-deploy-app-only.sh [SERVER]
#
# Environment:
#   DEPLOY_SERVER  - Default SSH target (default: kkotlowski@hp-homeserver)
#   DEPLOY_PATH    - Remote path (default: /opt/jobseeker)
#   RUN_TESTS      - 1 (default) to run local tests, 0 to skip
#   TEST_DATABASE_URL - Optional backend test DB URL

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly DEFAULT_SERVER="${DEPLOY_SERVER:-kkotlowski@hp-homeserver}"
readonly DEFAULT_PATH="${DEPLOY_PATH:-/opt/jobseeker}"
readonly COMPOSE_FILE="deploy/docker-compose.prod.yml"
readonly DEFAULT_THIN_LLAMA_GIT_URL="https://github.com/krzysztofkotlowski/thin-llama.git"
readonly DEFAULT_THIN_LLAMA_GIT_REF="b6235a57899ec466e892b9361babf72aaecfcea1"

SERVER="${1:-${DEFAULT_SERVER}}"
REMOTE_PATH="${DEPLOY_PATH:-${DEFAULT_PATH}}"
RUN_TESTS="${RUN_TESTS:-1}"
readonly REMOTE_THIN_LLAMA_PATH="${REMOTE_THIN_LLAMA_PATH:-$(dirname "${REMOTE_PATH}")/thin-llama}"
THIN_LLAMA_GIT_URL="${THIN_LLAMA_GIT_URL:-}"
THIN_LLAMA_GIT_REF="${THIN_LLAMA_GIT_REF:-}"
THIN_LLAMA_VERSION="${THIN_LLAMA_VERSION:-}"
THIN_LLAMA_BUILD_DATE="${THIN_LLAMA_BUILD_DATE:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

log() { echo "[test-deploy-app-only]" "$@"; }
err() { echo "[test-deploy-app-only] ERROR:" "$@" >&2; }

wait_local_postgres() {
  for _ in {1..30}; do
    if docker compose exec -T postgres pg_isready -U jobseeker -q 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_local_elasticsearch() {
  for _ in {1..30}; do
    if curl -sf http://localhost:9200/_cluster/health >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

run_local_tests() {
  if [[ "${RUN_TESTS}" != "1" ]]; then
    log "RUN_TESTS=0 -> skipping local tests."
    return 0
  fi

  log "Preparing local test services..."
  docker compose up -d postgres elasticsearch >/dev/null

  if ! wait_local_postgres; then
    err "Local Postgres did not become ready."
    exit 1
  fi
  if ! wait_local_elasticsearch; then
    err "Local Elasticsearch did not become ready."
    exit 1
  fi

  docker compose exec -T postgres psql -U jobseeker -c "CREATE DATABASE jobseeker_test" >/dev/null 2>&1 || true

  log "Running backend lint/tests..."
  cd "${PROJECT_ROOT}/backend"
  pip install -q -r requirements.txt
  ruff check app
  export DATABASE_URL="${TEST_DATABASE_URL:-postgresql://jobseeker:jobseeker@localhost:5432/jobseeker_test}"
  python3 -m pytest tests/ -v --tb=short

  log "Running frontend lint/tests..."
  cd "${PROJECT_ROOT}/frontend"
  npm run lint
  npm run test -- --run

  cd "${PROJECT_ROOT}"
}

sync_project() {
  log "Syncing job-seeker to ${SERVER}:${REMOTE_PATH}..."
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
}

ensure_remote_env() {
  if ! ssh "${SERVER}" "test -f '${REMOTE_PATH}/.env'"; then
    log "Creating remote .env from template..."
    ssh "${SERVER}" "cp '${REMOTE_PATH}/deploy/env.example.prod' '${REMOTE_PATH}/.env'"
    log "Edit ${REMOTE_PATH}/.env on server and set secure POSTGRES_PASSWORD."
  fi
}

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

ensure_remote_thin_llama_checkout() {
  log "Fetching thin-llama from Git (${THIN_LLAMA_GIT_URL} @ ${THIN_LLAMA_GIT_REF})..."
  ssh "${SERVER}" "set -euo pipefail; mkdir -p '$(dirname "${REMOTE_THIN_LLAMA_PATH}")'; if [ ! -d '${REMOTE_THIN_LLAMA_PATH}/.git' ]; then git clone '${THIN_LLAMA_GIT_URL}' '${REMOTE_THIN_LLAMA_PATH}'; fi; cd '${REMOTE_THIN_LLAMA_PATH}'; git fetch --tags origin; git checkout --detach '${THIN_LLAMA_GIT_REF}'; git submodule update --init --recursive >/dev/null 2>&1 || true; git rev-parse --short HEAD"
}

ensure_remote_service_running_without_recreate() {
  local service="$1"
  local exists=""
  exists="$(ssh "${SERVER}" "cd '${REMOTE_PATH}' && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f '${COMPOSE_FILE}' ps -a -q '${service}'" || true)"
  if [[ -z "${exists}" ]]; then
    log "Remote ${service} container missing -> creating it once."
    ssh "${SERVER}" "cd '${REMOTE_PATH}' && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f '${COMPOSE_FILE}' up -d '${service}'"
  else
    ssh "${SERVER}" "cd '${REMOTE_PATH}' && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f '${COMPOSE_FILE}' start '${service}' >/dev/null 2>&1 || true"
  fi
}

deploy_app_only() {
  # Do not redeploy DB/search unless missing.
  ensure_remote_service_running_without_recreate postgres
  ensure_remote_service_running_without_recreate elasticsearch
  ensure_remote_service_running_without_recreate redis

  log "Deploying thin-llama runtime..."
  ssh "${SERVER}" "cd '${REMOTE_PATH}' && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f '${COMPOSE_FILE}' up -d --build --remove-orphans thin-llama"
}

bootstrap_remote_self_hosted() {
  log "Bootstrapping thin-llama models..."
  ssh "${SERVER}" "cd '${REMOTE_PATH}' && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f '${COMPOSE_FILE}' run --rm thin-llama-init"

  log "Deploying app services only (backend/frontend/worker, no DB/search rebuild)..."
  ssh "${SERVER}" "cd '${REMOTE_PATH}' && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f '${COMPOSE_FILE}' up -d --build --no-deps --remove-orphans backend frontend worker"
}

check_remote_backend_health_once() {
  # Preferred: through frontend reverse proxy (port 80 published in prod).
  if ssh "${SERVER}" "health=\$(curl -sf http://127.0.0.1/api/v1/health) && printf '%s' \"\${health}\" | grep -q '\"llm_available\":true'"; then
    return 0
  fi
  # Fallback: inside backend container.
  ssh "${SERVER}" \
    "cd '${REMOTE_PATH}' && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f '${COMPOSE_FILE}' exec -T backend python -c \"import json, sys, urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=5)); sys.exit(0 if data.get('llm_available') else 1)\"" \
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

  err "Remote backend health check failed after retries."
  log "Diagnostics: docker compose ps"
  ssh "${SERVER}" "cd '${REMOTE_PATH}' && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f '${COMPOSE_FILE}' ps" || true
  log "Diagnostics: backend logs (last 120 lines)"
  ssh "${SERVER}" "cd '${REMOTE_PATH}' && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f '${COMPOSE_FILE}' logs --tail=120 backend" || true
  log "Diagnostics: thin-llama /health"
  ssh "${SERVER}" "cd '${REMOTE_PATH}' && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f '${COMPOSE_FILE}' exec -T thin-llama curl -sS http://127.0.0.1:8080/health" || true
  log "Diagnostics: thin-llama /api/models"
  ssh "${SERVER}" "cd '${REMOTE_PATH}' && THIN_LLAMA_BUILD_CONTEXT='${REMOTE_THIN_LLAMA_PATH}' THIN_LLAMA_GIT_REF='${THIN_LLAMA_GIT_REF}' THIN_LLAMA_VERSION='${THIN_LLAMA_VERSION}' THIN_LLAMA_BUILD_DATE='${THIN_LLAMA_BUILD_DATE}' docker compose -f '${COMPOSE_FILE}' exec -T thin-llama curl -sS http://127.0.0.1:8080/api/models" || true
  exit 1
}

verify_frontend_health() {
  log "Verifying remote frontend health..."
  for _ in $(seq 1 30); do
    if ssh "${SERVER}" "curl -sf http://127.0.0.1/ >/dev/null"; then
      log "Remote frontend health is OK."
      return 0
    fi
    sleep 2
  done
  err "Remote frontend health check failed."
  exit 1
}

main() {
  cd "${PROJECT_ROOT}"
  run_local_tests
  sync_project
  ensure_remote_env
load_thin_llama_git_config
if [[ -z "${THIN_LLAMA_VERSION}" ]]; then
  THIN_LLAMA_VERSION="${THIN_LLAMA_GIT_REF:0:7}"
fi
  ensure_remote_thin_llama_checkout
  deploy_app_only
  bootstrap_remote_self_hosted
  verify_remote_health
  verify_frontend_health
  log "Done. App deploy completed without unnecessary DB/search redeployment."
}

main "$@"
