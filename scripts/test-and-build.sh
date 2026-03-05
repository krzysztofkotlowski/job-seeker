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
docker compose up postgres -d
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
echo "Creating jobseeker_test database if not exists..."
docker compose exec -T postgres psql -U jobseeker -c "CREATE DATABASE jobseeker_test" 2>/dev/null || true
echo "Environment ready."

echo ""
echo "=== 1. Backend tests ==="
cd backend
pip install -q -r requirements.txt
export DATABASE_URL="${TEST_DATABASE_URL:-postgresql://jobseeker:jobseeker@localhost:5432/jobseeker_test}"
if ! python3 -m pytest tests/ -v --tb=short; then
  echo "Backend tests failed."
  exit 1
fi
cd "$ROOT"

echo ""
echo "=== 2. Frontend tests ==="
cd frontend
if ! npm run test -- --run; then
  echo "Frontend tests failed."
  exit 1
fi
cd "$ROOT"

echo ""
echo "=== 3. Docker build and up ==="
docker compose up --build -d

echo ""
echo "=== 4. Pull Ollama model (for resume AI summary) ==="
echo "Waiting for Ollama to be ready..."
for i in {1..60}; do
  if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "Pulling tinyllama (this may take a few minutes on first run)..."
  docker compose exec -T ollama ollama pull tinyllama
  echo "Model ready."
else
  echo "Ollama not reachable; resume summaries will be disabled. Run: docker compose exec ollama ollama pull tinyllama"
fi

echo ""
echo "Done. Frontend: http://localhost:5173  Backend: http://localhost:8000"
