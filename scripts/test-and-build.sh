#!/usr/bin/env bash
# Test and build pipeline for Job Seeker Tracker.
# Run from project root. On success, starts services via docker compose.
#
# Prerequisites: Python 3, pip, Node.js, npm, Docker
# Script auto-starts Postgres and creates jobseeker_test DB if needed.

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== 0. Prepare test environment ==="
docker compose up postgres elasticsearch -d
echo "Waiting for Postgres to be ready..."
for i in {1..30}; do
  if docker compose exec -T postgres pg_isready -U jobseeker -q 2>/dev/null; then
    break
  fi
  sleep 1
done
if ! docker compose exec -T postgres pg_isready -U jobseeker -q 2>/dev/null; then
  echo "Postgres failed to become ready."
  exit 1
fi
echo "Waiting for Elasticsearch to be ready (up to 60s)..."
for i in {1..30}; do
  if curl -sf http://localhost:9200/_cluster/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
echo "Creating jobseeker_test database if not exists..."
docker compose exec -T postgres psql -U jobseeker -c "CREATE DATABASE jobseeker_test" 2>/dev/null || true
echo "Environment ready."

echo ""
echo "=== 1. Backend lint and tests ==="
cd backend
pip install -q -r requirements.txt
if ! ruff check app; then
  echo "Backend lint (ruff) failed."
  exit 1
fi
export DATABASE_URL="${TEST_DATABASE_URL:-postgresql://jobseeker:jobseeker@localhost:5432/jobseeker_test}"
if ! python3 -m pytest tests/ -v --tb=short --cov=app --cov-report=term-missing; then
  echo "Backend tests failed."
  exit 1
fi
cd "$ROOT"

echo ""
echo "=== 2. Frontend lint and tests ==="
cd frontend
if ! npm run lint; then
  echo "Frontend lint failed."
  exit 1
fi
if ! npm run test -- --run; then
  echo "Frontend tests failed."
  exit 1
fi
cd "$ROOT"

echo ""
echo "=== 3. Docker build and up ==="
docker compose --compatibility up --build -d

echo ""
echo "=== 4. thin-llama: ensure runtime and models are ready ==="
echo "Starting thin-llama if not already running..."
docker compose --compatibility up -d thin-llama 2>/dev/null || true
echo "Waiting for thin-llama API (up to 120s)..."
THIN_LLAMA_READY=0
for i in $(seq 1 60); do
  if curl -sf http://localhost:18080/health >/dev/null 2>&1; then
    THIN_LLAMA_READY=1
    echo "thin-llama is ready."
    break
  fi
  printf "."
  sleep 2
done
echo ""
if [ "$THIN_LLAMA_READY" -eq 0 ]; then
  echo "WARNING: thin-llama not reachable after 120s. Resume summaries will be disabled."
  echo "  Start manually: docker compose up -d thin-llama"
  echo "  Then bootstrap models: docker compose run --rm thin-llama-init"
else
  echo "Bootstrapping qwen2.5:7b and bge-base-en:v1.5..."
  if ! docker compose run --rm thin-llama-init; then
    echo "ERROR: Failed to bootstrap thin-llama models. AI summaries and RAG will not work."
    exit 1
  fi
  echo "thin-llama models ready."
fi

echo ""
echo "=== 5. Verify containers ==="
if curl -sf http://localhost:9200/_cluster/health >/dev/null 2>&1; then
  echo "Elasticsearch: OK"
else
  echo "Elasticsearch: not reachable"
fi
if curl -sf http://localhost:18080/health >/dev/null 2>&1; then
  echo "thin-llama: OK"
else
  echo "thin-llama: not reachable"
fi
if curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1; then
  echo "Backend: OK"
else
  echo "Backend: not reachable"
fi

echo ""
echo "Done. Frontend: http://localhost:5173  Backend: http://localhost:8000"
