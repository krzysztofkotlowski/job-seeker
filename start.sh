#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
    echo "Shutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    echo "Done."
}
trap cleanup EXIT INT TERM

echo "Starting Job Seeker Tracker..."

cd "$SCRIPT_DIR/backend"
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "Backend started (PID: $BACKEND_PID) on http://localhost:8000"

sleep 2

cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!
echo "Frontend started (PID: $FRONTEND_PID) on http://localhost:5173"

echo ""
echo "========================================="
echo "  Job Seeker Tracker is running!"
echo "  Open http://localhost:5173 in your browser"
echo "  Press Ctrl+C to stop"
echo "========================================="
echo ""

wait
