import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Slider from "@mui/material/Slider";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import type { SelectChangeEvent } from "@mui/material/Select";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import { LoadingSpinner } from "./LoadingSpinner";
import { api } from "../api/client";
import type {
  AIConfig,
  AIConfigUpdate,
  AIProvider,
  AIEmbedSource,
  OllamaModel,
  AIMetrics,
} from "../api/types";
import { useToast } from "../contexts/useToast";

const OLLAMA_LLM_OPTIONS = [
  "qwen2.5:7b",
  "qwen3:4b",
  "qwen3:8b",
  "llama3.2:3b",
  "phi3:mini",
];
const DEFAULT_LLM_MODEL = "qwen2.5:7b";

const EMBED_FAMILIES = ["nomic", "all-minilm", "mxbai", "bge"];

// Chat completion models (March 2026) — frontier first, then legacy
const OPENAI_LLM_MODELS = [
  "gpt-5.4",
  "gpt-5.4-pro",
  "gpt-5-mini",
  "gpt-5-nano",
  "gpt-5",
  "gpt-4.1",
  "gpt-4.1-mini",
  "gpt-4.1-nano",
  "gpt-4o",
  "gpt-4o-mini",
  "gpt-4-turbo",
  "gpt-4",
  "gpt-3.5-turbo",
];

function isEmbeddingModel(m: OllamaModel): boolean {
  const name = (m.name || m.model || "").toLowerCase();
  return EMBED_FAMILIES.some((f) => name.includes(f)) || name.includes("embed");
}

export function AIConfigContent() {
  const toast = useToast();
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [config, setConfig] = useState<AIConfig | null>(null);
  const [metrics, setMetrics] = useState<AIMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [ensuringModel, setEnsuringModel] = useState(false);
  const [validating, setValidating] = useState(false);
  const [llmAvailable, setLlmAvailable] = useState<boolean | null>(null);

  const [provider, setProvider] = useState<AIProvider>("ollama");
  const [openaiApiKey, setOpenaiApiKey] = useState("");
  const [openaiLlmModel, setOpenaiLlmModel] = useState("gpt-4o-mini");
  const [embedSource, setEmbedSource] = useState<AIEmbedSource>("ollama");
  const [llmModel, setLlmModel] = useState("");
  const [embedModel, setEmbedModel] = useState("");
  const [temperature, setTemperature] = useState(0.3);
  const [maxOutputTokens, setMaxOutputTokens] = useState(1024);

  const fetchModels = (p: AIProvider) => {
    api
      .aiListModels(p)
      .then((res) => setModels(res.models || []))
      .catch(() => setModels([]));
  };

  useEffect(() => {
    Promise.all([
      api.aiGetConfig(),
      fetch("/api/v1/health")
        .then((r) => r.json())
        .then((h: { llm_available?: boolean }) =>
          setLlmAvailable(h.llm_available ?? false),
        )
        .catch(() => setLlmAvailable(false)),
    ])
      .then(([cfg]) => {
        const p = (cfg.provider as AIProvider) || "ollama";
        setConfig(cfg);
        setProvider(p);
        setOpenaiLlmModel(cfg.openai_llm_model || "gpt-4o-mini");
        setEmbedSource((cfg.embed_source as AIEmbedSource) || "ollama");
        setLlmModel(cfg.llm_model || DEFAULT_LLM_MODEL);
        setEmbedModel(cfg.embed_model);
        setTemperature(cfg.temperature);
        setMaxOutputTokens(cfg.max_output_tokens);
      })
      .catch((e) =>
        toast.showError(
          e instanceof Error ? e.message : "Failed to load AI config",
        ),
      )
      .finally(() => setLoading(false));
  }, [toast]);

  useEffect(() => {
    if (!loading) fetchModels(provider);
  }, [provider, loading]);

  useEffect(() => {
    api
      .aiGetMetrics()
      .then(setMetrics)
      .catch(() => setMetrics(null));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    const payload: AIConfigUpdate = {
      provider,
      openai_llm_model: openaiLlmModel,
      embed_source: embedSource,
      temperature,
      max_output_tokens: maxOutputTokens,
    };
    if (provider === "ollama")
      payload.llm_model = (llmModel || DEFAULT_LLM_MODEL).trim();
    if (embedModel?.trim()) payload.embed_model = embedModel.trim();
    if (provider === "openai" && openaiApiKey.trim()) {
      payload.openai_api_key = openaiApiKey.trim();
    }
    try {
      if (provider === "ollama" && payload.llm_model) {
        setEnsuringModel(true);
        const ensure = await api.aiEnsureModel(payload.llm_model);
        setEnsuringModel(false);
        if (ensure.status === "error") {
          toast.showError(ensure.error || "Failed to ensure model");
          setSaving(false);
          return;
        }
      }
      const updated = await api.aiUpdateConfig(payload);
      setConfig(updated);
      setOpenaiApiKey("");
      toast.showSuccess("AI config saved");
      if (provider === "ollama") {
        fetchModels("ollama");
        fetch("/api/v1/health")
          .then((r) => r.json())
          .then((h: { llm_available?: boolean }) =>
            setLlmAvailable(h.llm_available ?? false),
          )
          .catch(() => setLlmAvailable(false));
      }
    } catch (e) {
      toast.showError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (config) {
      setProvider((config.provider as AIProvider) || "ollama");
      setOpenaiLlmModel(config.openai_llm_model || "gpt-4o-mini");
      setEmbedSource((config.embed_source as AIEmbedSource) || "ollama");
      setLlmModel(config.llm_model || DEFAULT_LLM_MODEL);
      setEmbedModel(config.embed_model);
      setTemperature(config.temperature);
      setMaxOutputTokens(config.max_output_tokens);
      setOpenaiApiKey("");
      toast.showSuccess("Reset to saved config");
    }
  };

  const canSave =
    provider === "ollama" ||
    config?.api_key_set === true ||
    (provider === "openai" && openaiApiKey.trim().length > 0);

  const llmModelsFromOllama = models.filter((m) => !isEmbeddingModel(m));
  const recommendedAsModels = OLLAMA_LLM_OPTIONS.map((name) => ({
    name,
    model: name,
  }));
  const pulledNames = new Set(llmModelsFromOllama.map((m) => m.name));
  const llmSelectOptions =
    provider === "ollama"
      ? [
          ...llmModelsFromOllama,
          ...recommendedAsModels.filter((m) => !pulledNames.has(m.name)),
        ]
      : llmModelsFromOllama;
  const llmSelectValue = llmModel || DEFAULT_LLM_MODEL;
  let embedModels = models.filter((m) => isEmbeddingModel(m));
  if (embedModels.length === 0) embedModels = [...models];

  const embedOptions = [...embedModels];
  const embedBase = embedModel?.split(":")[0] || "";
  const embedModelInList = embedOptions.some(
    (m) =>
      m.name === embedModel || (embedBase && m.name?.startsWith(embedBase)),
  );
  if (embedModel && !embedModelInList) {
    embedOptions.unshift({ name: embedModel, model: embedModel });
  }

  const embedSelectValue =
    embedOptions.find(
      (m) =>
        m.name === embedModel || (embedBase && m.name?.startsWith(embedBase)),
    )?.name ?? embedModel;

  if (loading) {
    return <LoadingSpinner />;
  }

  const formContent = (
    <>
      <Paper sx={{ p: 3 }}>
        <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
          AI provider
        </Typography>
        <ToggleButtonGroup
          value={provider}
          exclusive
          onChange={(_, v) => v && setProvider(v as AIProvider)}
          size="small"
        >
          <ToggleButton value="ollama">Self-hosted (Ollama)</ToggleButton>
          <ToggleButton value="openai">OpenAI API</ToggleButton>
        </ToggleButtonGroup>
      </Paper>

      {provider === "ollama" && (
        <>
          {llmAvailable === false && (
            <Alert severity="warning">
              Ollama is not available. Start Ollama and pull a model (e.g.
              ollama pull qwen2.5:7b) to use AI summaries.
            </Alert>
          )}

          <Paper sx={{ p: 3 }}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
              Model selection
            </Typography>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <FormControl fullWidth size="small">
                <InputLabel>LLM model</InputLabel>
                <Select
                  value={llmSelectValue}
                  label="LLM model"
                  onChange={(e: SelectChangeEvent) =>
                    setLlmModel(e.target.value)
                  }
                >
                  {llmSelectOptions.map((m) => (
                    <MenuItem key={m.name} value={m.name}>
                      {m.name}
                      {"details" in m && m.details?.parameter_size && (
                        <Typography
                          component="span"
                          variant="caption"
                          sx={{ ml: 1, opacity: 0.7 }}
                        >
                          ({m.details.parameter_size})
                        </Typography>
                      )}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              <FormControl fullWidth size="small">
                <InputLabel>Embedding model (RAG)</InputLabel>
                <Select
                  value={embedSelectValue}
                  label="Embedding model (RAG)"
                  onChange={(e: SelectChangeEvent) =>
                    setEmbedModel(e.target.value)
                  }
                >
                  {embedOptions.map((m) => (
                    <MenuItem key={m.name} value={m.name}>
                      {m.name}
                    </MenuItem>
                  ))}
                  {embedOptions.length === 0 && (
                    <MenuItem value={embedModel} disabled>
                      {embedModel || "No embedding models"}
                    </MenuItem>
                  )}
                </Select>
              </FormControl>
            </Box>
          </Paper>
        </>
      )}

      {provider === "openai" && (
        <Paper sx={{ p: 3 }}>
          <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
            OpenAI configuration
          </Typography>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
              {config?.api_key_set ? (
                <Chip label="Key configured" color="success" size="small" />
              ) : (
                <Chip label="No key" color="default" size="small" />
              )}
            </Box>
            <TextField
              fullWidth
              size="small"
              type="password"
              label="OpenAI API key"
              placeholder="sk-..."
              value={openaiApiKey}
              onChange={(e) => setOpenaiApiKey(e.target.value)}
              helperText="Stored securely. Leave blank to keep existing key."
            />
            <Box sx={{ display: "flex", gap: 1 }}>
              <Button
                variant="outlined"
                size="small"
                disabled={!openaiApiKey.trim() || validating}
                onClick={async () => {
                  const key = openaiApiKey.trim();
                  if (!key) return;
                  setValidating(true);
                  try {
                    const res = await api.aiValidateOpenAIKey(key);
                    if (res.valid) {
                      toast.showSuccess("API key is valid");
                    } else {
                      toast.showError(res.error || "Invalid key");
                    }
                  } catch (e) {
                    toast.showError(
                      e instanceof Error ? e.message : "Validation failed",
                    );
                  } finally {
                    setValidating(false);
                  }
                }}
              >
                {validating ? "Testing…" : "Test connection"}
              </Button>
            </Box>
            <FormControl fullWidth size="small">
              <InputLabel>LLM model</InputLabel>
              <Select
                value={openaiLlmModel}
                label="LLM model"
                onChange={(e: SelectChangeEvent) =>
                  setOpenaiLlmModel(e.target.value)
                }
              >
                {OPENAI_LLM_MODELS.map((m) => (
                  <MenuItem key={m} value={m}>
                    {m}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Box>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Embedding source (RAG)
              </Typography>
              <RadioGroup
                value={embedSource}
                onChange={(e) =>
                  setEmbedSource(e.target.value as AIEmbedSource)
                }
              >
                <FormControlLabel
                  value="openai"
                  control={<Radio size="small" />}
                  label="OpenAI (text-embedding-3-small) — requires re-sync"
                />
                <FormControlLabel
                  value="ollama"
                  control={<Radio size="small" />}
                  label="Ollama (if available)"
                />
              </RadioGroup>
            </Box>
          </Box>
        </Paper>
      )}

      <Paper sx={{ p: 3 }}>
        <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
          Parameters
        </Typography>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <Box>
            <Typography gutterBottom>
              Temperature: {temperature.toFixed(2)} (lower = more focused)
            </Typography>
            <Slider
              value={temperature}
              onChange={(_, v) => setTemperature(v as number)}
              min={0}
              max={1}
              step={0.05}
              valueLabelDisplay="auto"
            />
          </Box>
          <Box>
            <Typography gutterBottom>
              Max output tokens: {maxOutputTokens}
            </Typography>
            <Slider
              value={maxOutputTokens}
              onChange={(_, v) => setMaxOutputTokens(v as number)}
              min={512}
              max={4096}
              step={256}
              valueLabelDisplay="auto"
            />
          </Box>
        </Box>
      </Paper>

      {metrics && metrics.total_requests > 0 && (
        <Paper sx={{ p: 3 }}>
          <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
            Metrics (last 7 days)
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
            <Chip label={`Requests: ${metrics.total_requests}`} />
            {metrics.avg_latency_ms != null && (
              <Chip
                label={`Avg latency: ${Math.round(metrics.avg_latency_ms)} ms`}
              />
            )}
            <Chip label={`Input tokens: ${metrics.total_input_tokens}`} />
            <Chip label={`Output tokens: ${metrics.total_output_tokens}`} />
          </Box>
          {metrics.by_model && metrics.by_model.length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                By model:
              </Typography>
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
                {metrics.by_model.map((b) => (
                  <Chip
                    key={b.model}
                    label={`${b.model}: ${b.count}`}
                    size="small"
                    variant="outlined"
                  />
                ))}
              </Box>
            </Box>
          )}
        </Paper>
      )}
    </>
  );

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        flex: 1,
        minHeight: 0,
      }}
    >
      <Box
        sx={{
          flex: 1,
          overflow: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 3,
        }}
      >
        {formContent}
      </Box>
      <Box
        sx={{
          flexShrink: 0,
          pt: 2,
          borderTop: 1,
          borderColor: "divider",
        }}
      >
        <Box sx={{ display: "flex", gap: 2 }}>
          <Button
            variant="contained"
            onClick={handleSave}
            disabled={saving || !canSave}
          >
            {saving
              ? ensuringModel
                ? "Ensuring model…"
                : "Saving…"
              : "Save"}
          </Button>
          <Button variant="outlined" onClick={handleReset} disabled={!config}>
            Reset to saved
          </Button>
        </Box>
      </Box>
    </Box>
  );
}
