#!/bin/sh
set -eu

THIN_LLAMA_URL="${THIN_LLAMA_URL:-http://thin-llama:8080}"
EMBED_MODEL="${EMBED_MODEL:-all-minilm}"
LLM_MODEL="${LLM_MODEL:-qwen2.5:3b}"

wait_for_runtime() {
  ready=0
  health_json=""
  models_json=""
  for _ in $(seq 1 30); do
    health_json="$(curl -sS "$THIN_LLAMA_URL/health")"
    models_json="$(curl -sS "$THIN_LLAMA_URL/api/models")"
    if printf '%s' "$health_json" | grep -Eq '"last_error":"[^"]+'; then
      echo "thin-llama reported a model startup error:"
      echo "$health_json"
      echo "$models_json"
      exit 1
    fi
    if printf '%s' "$models_json" | grep -Eq '"download_error":"[^"]+|"runtime_error":"[^"]+|"runtime_message":"[^"]+'; then
      echo "thin-llama reported model errors:"
      echo "$health_json"
      echo "$models_json"
      exit 1
    fi
    if printf '%s' "$health_json" | grep -q '"restart_suppressed":true' || printf '%s' "$models_json" | grep -q '"restart_suppressed":true'; then
      echo "thin-llama suppressed restarts after repeated failures:"
      echo "$health_json"
      echo "$models_json"
      exit 1
    fi
    if printf '%s' "$health_json" | grep -q '"runtime_ready":true' &&
       printf '%s' "$models_json" | grep -Eq '"active":true[^\n]*"role":"chat"[^\n]*"runtime_ready":true' &&
       printf '%s' "$models_json" | grep -Eq '"active":true[^\n]*"role":"embedding"[^\n]*"runtime_ready":true'; then
      ready=1
      break
    fi
    sleep 2
  done
  if [ "$ready" -ne 1 ]; then
    echo "thin-llama models did not become ready in time."
    echo "$health_json"
    echo "$models_json"
    exit 1
  fi
  echo "$health_json"
  echo "$models_json"
}

post_json() {
  endpoint="$1"
  body="$2"
  outfile="$3"
  code="$(curl -sS -o "$outfile" -w "%{http_code}" -X POST "$THIN_LLAMA_URL$endpoint" -H 'Content-Type: application/json' -d "$body")"
  if [ "$code" -lt 200 ] || [ "$code" -ge 300 ]; then
    echo "Request to $endpoint failed with status $code"
    cat "$outfile"
    exit 1
  fi
  cat "$outfile"
}

echo "Waiting for thin-llama control plane..."
for _ in $(seq 1 30); do
  if curl -sf "$THIN_LLAMA_URL/health" >/dev/null; then
    echo "thin-llama control plane ready."
    break
  fi
  sleep 2
done

echo "Pulling embedding model: $EMBED_MODEL"
post_json "/api/pull" "{\"model\":\"$EMBED_MODEL\"}" /tmp/embed-pull.out

echo "Pulling chat model: $LLM_MODEL"
post_json "/api/pull" "{\"model\":\"$LLM_MODEL\"}" /tmp/chat-pull.out

echo "Activating models..."
post_json "/api/models/active" "{\"chat\":\"$LLM_MODEL\",\"embedding\":\"$EMBED_MODEL\"}" /tmp/activate.out

echo "Waiting for runtime-ready models..."
wait_for_runtime

echo "Running chat smoke test..."
post_json "/api/chat" "{\"model\":\"$LLM_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with: OK\"}],\"stream\":false}" /tmp/chat-smoke.out
if ! grep -q '"done":true' /tmp/chat-smoke.out; then
  echo "Chat smoke test did not return a completed response."
  cat /tmp/chat-smoke.out
  exit 1
fi

echo "Running embedding smoke test..."
post_json "/api/embed" "{\"model\":\"$EMBED_MODEL\",\"input\":\"hello world\"}" /tmp/embed-smoke.out
if ! grep -q '"embeddings"' /tmp/embed-smoke.out; then
  echo "Embedding smoke test did not return embeddings."
  cat /tmp/embed-smoke.out
  exit 1
fi

echo "Re-checking runtime after smoke tests..."
wait_for_runtime
echo "Models ready."
