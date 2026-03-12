# thin-llama + Job Seeker Integration

Job Seeker Tracker uses [thin-llama](https://github.com/krzysztofkotlowski/thin-llama) as the default self-hosted AI runtime for both chat (resume summaries, career guidance) and embeddings (RAG).

## Role

- **Chat:** `qwen2.5:7b` (or configurable) for generating job summaries and career advice.
- **Embeddings:** `nomic-embed-text` (768 dimensions) for semantic search over job descriptions.

## Integration points

1. **Backend / worker:** `LLM_URL` points to thin-llama (e.g. `http://thin-llama:8080`). The backend uses the same OpenAI-compatible client for thin-llama and OpenAI; thin-llama exposes an Ollama-compatible API that maps to this interface.

2. **Bootstrap:** The `thin-llama-init` one-shot service pulls the configured chat and embedding models, activates them, and runs smoke tests. Backend and worker depend on `thin-llama-init` completing successfully.

3. **Production:** Deploy scripts fetch thin-llama from a pinned Git ref on the server and build the runtime image. No Ollama container is used.

## Configuration

| Variable    | Purpose                          | Default            |
|------------|-----------------------------------|--------------------|
| `LLM_URL`  | thin-llama API base URL          | `http://thin-llama:8080` |
| `LLM_MODEL`| Chat model name                  | `qwen2.5:7b`       |
| `EMBED_MODEL` | Embedding model name          | `nomic-embed-text` |
| `EMBED_DIMS`  | Vector dimensions (must match model) | `768`          |

## thin-llama vs Ollama

- **thin-llama:** Minimal Go control plane for llama.cpp. Lightweight, single-binary, Ollama-compatible API. Used by Job Seeker for self-hosted inference.
- **Ollama:** Full-featured runtime with more models and tooling. Heavier; Job Seeker does not use it in production.
