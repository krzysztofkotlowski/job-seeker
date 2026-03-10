#!/usr/bin/env bash
# Test locally, then deploy to production server.
#
# Runs backend + frontend lint and tests. On success, syncs to server and
# starts Docker Compose. Use after making code changes (e.g. LLM config, features).
#
# Usage:
#   ./deploy/scripts/test-and-deploy.sh [SERVER]
#
# Examples:
#   ./deploy/scripts/test-and-deploy.sh
#   ./deploy/scripts/test-and-deploy.sh kkotlowski@hp-homeserver
#
# Prerequisites: Python 3, pip, Node.js, npm, Docker, SSH access to server

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly DEFAULT_SERVER="${DEPLOY_SERVER:-kkotlowski@hp-homeserver}"

SERVER="${1:-${DEFAULT_SERVER}}"

log() { echo "[test-and-deploy]" "$@"; }

cd "${PROJECT_ROOT}"

# --- 1. Prepare test environment ---
log "Preparing test environment..."
docker compose up postgres elasticsearch -d 2>/dev/null || true
echo "Waiting for Postgres..."
for i in {1..30}; do
  if docker compose exec -T postgres pg_isready -U jobseeker -q 2>/dev/null; then
    break
  fi
  sleep 1
done
if ! docker compose exec -T postgres pg_isready -U jobseeker -q 2>/dev/null; then
  log "Postgres failed to become ready."
  exit 1
fi
echo "Waiting for Elasticsearch..."
for i in {1..30}; do
  if curl -sf http://localhost:9200/_cluster/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker compose exec -T postgres psql -U jobseeker -c "CREATE DATABASE jobseeker_test" 2>/dev/null || true

# --- 2. Backend lint and tests ---
log "Running backend lint and tests..."
cd backend
pip install -q -r requirements.txt
ruff check app
export DATABASE_URL="${TEST_DATABASE_URL:-postgresql://jobseeker:jobseeker@localhost:5432/jobseeker_test}"
python3 -m pytest tests/ -v --tb=short
cd "${PROJECT_ROOT}"

# --- 3. Frontend lint and tests ---
log "Running frontend lint and tests..."
cd frontend
npm run lint
npm run test -- --run
cd "${PROJECT_ROOT}"

# --- 4. Deploy ---
log "All tests passed. Deploying to ${SERVER}..."
bash "${SCRIPT_DIR}/deploy.sh" "${SERVER}"

log "Done. App: http://<server-ip>"
