#!/usr/bin/env bash
# Migrate PostgreSQL database from local Docker to production server
#
# Dumps the local jobseeker DB, copies it to the server, and restores.
# Requires: local postgres running (docker compose up postgres), SSH access to server.
#
# Usage:
#   ./deploy/scripts/migrate-db-to-server.sh [SERVER]
#
# Examples:
#   ./deploy/scripts/migrate-db-to-server.sh
#   ./deploy/scripts/migrate-db-to-server.sh kkotlowski@hp-homeserver

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly DEFAULT_SERVER="${DEPLOY_SERVER:-kkotlowski@hp-homeserver}"
readonly REMOTE_PATH="${DEPLOY_PATH:-/opt/jobseeker}"
readonly DUMP_FILE="jobseeker_migration_$(date +%Y%m%d_%H%M%S).sql"

SERVER="${1:-${DEFAULT_SERVER}}"

log() { echo "[migrate-db]" "$@"; }
log_err() { echo "[migrate-db] ERROR:" "$@" >&2; }

# --- Preflight ---
cd "${PROJECT_ROOT}"

if ! docker compose ps postgres 2>/dev/null | grep -q "Up"; then
  log_err "Local postgres is not running. Start it with: docker compose up postgres -d"
  exit 1
fi

# --- Dump from local ---
log "Dumping database from local postgres..."
docker compose exec -T postgres pg_dump -U jobseeker --clean --if-exists jobseeker > "/tmp/${DUMP_FILE}"
log "Dump saved: /tmp/${DUMP_FILE} ($(wc -l < "/tmp/${DUMP_FILE}") lines)"

# --- Copy to server ---
log "Copying dump to ${SERVER}..."
scp "/tmp/${DUMP_FILE}" "${SERVER}:/tmp/${DUMP_FILE}"

# --- Restore on server ---
log "Restoring database on server..."
ssh "${SERVER}" "cd ${REMOTE_PATH} && docker compose -f deploy/docker-compose.prod.yml exec -T postgres sh -c 'PGPASSWORD=\${POSTGRES_PASSWORD:-jobseeker} psql -U jobseeker jobseeker' < /tmp/${DUMP_FILE}"

# --- Cleanup ---
log "Removing dump from server..."
ssh "${SERVER}" "rm -f /tmp/${DUMP_FILE}"

log "Migration complete. You can remove the local dump: rm /tmp/${DUMP_FILE}"
