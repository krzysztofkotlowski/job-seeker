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
echo "=== 4. Ollama: ensure running and models pulled ==="
echo "Starting Ollama if not already running..."
docker compose --compatibility up -d ollama 2>/dev/null || true
echo "Waiting for Ollama API (up to 120s)..."
OLLAMA_READY=0
for i in $(seq 1 60); do
  if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    OLLAMA_READY=1
    echo "Ollama is ready."
    break
  fi
  printf "."
  sleep 2
done
echo ""
if [ "$OLLAMA_READY" -eq 0 ]; then
  echo "WARNING: Ollama not reachable after 120s. Resume summaries will be disabled."
  echo "  Start manually: docker compose up -d ollama"
  echo "  Then pull model: docker compose exec ollama ollama pull qwen2.5:7b"
else
  echo "Removing unused models (keeping qwen2.5 and nomic-embed-text)..."
  for full in $(docker compose exec -T ollama ollama list 2>/dev/null | awk 'NR>1 {print $1}'); do
    base="${full%%:*}"
    case "$base" in
      qwen2.5|nomic-embed-text) ;;
      *)
        echo "  Removing $full"
        docker compose exec -T ollama ollama rm "$full" 2>/dev/null || true
        ;;
    esac
  done
  echo "Pulling qwen2.5:7b (for resume AI summary)..."
  if ! docker compose exec -T ollama ollama pull qwen2.5:7b; then
    echo "ERROR: Failed to pull qwen2.5:7b. Resume summaries will not work."
    exit 1
  fi
  echo "Pulling nomic-embed-text (for RAG)..."
  if ! docker compose exec -T ollama ollama pull nomic-embed-text; then
    echo "ERROR: Failed to pull nomic-embed-text. RAG semantic search will not work."
    exit 1
  fi
  echo "Ollama models ready."
fi

echo ""
echo "=== 5. Verify containers ==="
if curl -sf http://localhost:9200/_cluster/health >/dev/null 2>&1; then
  echo "Elasticsearch: OK"
else
  echo "Elasticsearch: not reachable"
fi
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "Ollama: OK"
else
  echo "Ollama: not reachable"
fi
if curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1; then
  echo "Backend: OK"
else
  echo "Backend: not reachable"
fi

echo ""
echo "Done. Frontend: http://localhost:5173  Backend: http://localhost:8000"
