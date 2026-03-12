#!/bin/sh
set -eu

THIN_LLAMA_URL="${THIN_LLAMA_URL:-http://thin-llama:8080}"
EMBED_MODEL="${EMBED_MODEL:-bge-base-en:v1.5}"
LLM_MODEL="${LLM_MODEL:-qwen2.5:7b}"
SMOKE_ATTEMPTS="${SMOKE_ATTEMPTS:-12}"
SMOKE_DELAY_SECONDS="${SMOKE_DELAY_SECONDS:-3}"

extract_embedding_pid() {
  health_json="$1"
  printf '%s' "$health_json" | sed -n 's/.*"embedding":{"role":"embedding","model_name":"[^"]*","port":[0-9][0-9]*,"pid":\([0-9][0-9]*\).*/\1/p'
}

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
    if printf '%s' "$health_json" | grep -Fq '"runtime_ready":true' &&
       printf '%s' "$health_json" | grep -Fq "\"chat\":{\"role\":\"chat\",\"model_name\":\"$LLM_MODEL\"" &&
       printf '%s' "$health_json" | grep -Fq "\"embedding\":{\"role\":\"embedding\",\"model_name\":\"$EMBED_MODEL\""; then
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

post_json_retry() {
  endpoint="$1"
  body="$2"
  outfile="$3"
  attempts="$4"
  delay_seconds="$5"

  attempt=1
  while [ "$attempt" -le "$attempts" ]; do
    code="$(curl -sS -o "$outfile" -w "%{http_code}" -X POST "$THIN_LLAMA_URL$endpoint" -H 'Content-Type: application/json' -d "$body")"
    if [ "$code" -ge 200 ] && [ "$code" -lt 300 ]; then
      cat "$outfile"
      return 0
    fi
    if [ "$attempt" -lt "$attempts" ]; then
      echo "Request to $endpoint returned status $code on attempt $attempt/$attempts; retrying in ${delay_seconds}s..."
      sleep "$delay_seconds"
    fi
    attempt=$((attempt + 1))
  done

  echo "Request to $endpoint failed with status $code after $attempts attempts"
  cat "$outfile"
  exit 1
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
post_json_retry "/api/chat" "{\"model\":\"$LLM_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with: OK\"}],\"stream\":false}" /tmp/chat-smoke.out "$SMOKE_ATTEMPTS" "$SMOKE_DELAY_SECONDS"
if ! grep -q '"done":true' /tmp/chat-smoke.out; then
  echo "Chat smoke test did not return a completed response."
  cat /tmp/chat-smoke.out
  exit 1
fi

initial_health="$(curl -sS "$THIN_LLAMA_URL/health")"
initial_embed_pid="$(extract_embedding_pid "$initial_health")"
if [ -z "$initial_embed_pid" ]; then
  echo "Failed to determine embedding PID before smoke tests."
  echo "$initial_health"
  exit 1
fi

echo "Running repeated embedding smoke tests..."
for attempt in 1 2 3; do
  post_json_retry "/api/embed" "{\"model\":\"$EMBED_MODEL\",\"input\":[\"hello world\",\"vector search\"]}" "/tmp/embed-smoke-${attempt}.out" "$SMOKE_ATTEMPTS" "$SMOKE_DELAY_SECONDS"
  if ! grep -q '"embeddings"' "/tmp/embed-smoke-${attempt}.out"; then
    echo "Embedding smoke test ${attempt} did not return embeddings."
    cat "/tmp/embed-smoke-${attempt}.out"
    exit 1
  fi
done

echo "Re-checking runtime after smoke tests..."
wait_for_runtime
final_health="$(curl -sS "$THIN_LLAMA_URL/health")"
final_embed_pid="$(extract_embedding_pid "$final_health")"
if [ -z "$final_embed_pid" ] || [ "$initial_embed_pid" != "$final_embed_pid" ]; then
  echo "Embedding PID changed during smoke tests (initial=$initial_embed_pid final=${final_embed_pid:-missing})."
  echo "$initial_health"
  echo "$final_health"
  exit 1
fi
echo "Models ready."
