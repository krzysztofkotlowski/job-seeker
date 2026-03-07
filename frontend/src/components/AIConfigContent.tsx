import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Slider from "@mui/material/Slider";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import type { SelectChangeEvent } from "@mui/material/Select";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import { LoadingSpinner } from "./LoadingSpinner";
import { api } from "../api/client";
import type { AIConfig, OllamaModel, AIMetrics } from "../api/types";
import { useToast } from "../contexts/useToast";

const TINY_MODELS = [{ label: "TinyLlama", value: "tinyllama" }];

const EMBED_FAMILIES = ["nomic", "all-minilm", "mxbai", "bge"];

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
  const [llmAvailable, setLlmAvailable] = useState<boolean | null>(null);

  const [llmModel, setLlmModel] = useState("");
  const [embedModel, setEmbedModel] = useState("");
  const [temperature, setTemperature] = useState(0.3);
  const [maxOutputTokens, setMaxOutputTokens] = useState(1024);

  useEffect(() => {
    Promise.all([
      api.aiListModels(),
      api.aiGetConfig(),
      fetch("/api/v1/health")
        .then((r) => r.json())
        .then((h: { llm_available?: boolean }) =>
          setLlmAvailable(h.llm_available ?? false),
        )
        .catch(() => setLlmAvailable(false)),
    ])
      .then(([modelsRes, cfg]) => {
        setModels(modelsRes.models || []);
        setConfig(cfg);
        setLlmModel(cfg.llm_model);
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
    api
      .aiGetMetrics()
      .then(setMetrics)
      .catch(() => setMetrics(null));
  }, []);

  const handleSave = () => {
    setSaving(true);
    api
      .aiUpdateConfig({
        llm_model: llmModel,
        embed_model: embedModel,
        temperature,
        max_output_tokens: maxOutputTokens,
      })
      .then((updated) => {
        setConfig(updated);
        toast.showSuccess("AI config saved");
      })
      .catch((e) =>
        toast.showError(e instanceof Error ? e.message : "Failed to save"),
      )
      .finally(() => setSaving(false));
  };

  const handleReset = () => {
    if (config) {
      setLlmModel(config.llm_model);
      setEmbedModel(config.embed_model);
      setTemperature(config.temperature);
      setMaxOutputTokens(config.max_output_tokens);
      toast.showSuccess("Reset to saved config");
    }
  };

  const llmModels = models.filter((m) => !isEmbeddingModel(m));
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
      {llmAvailable === false && (
        <Alert severity="warning">
          Ollama is not available. Start Ollama and pull a model (e.g. ollama
          pull phi3:mini) to use AI summaries.
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
              value={llmModel}
              label="LLM model"
              onChange={(e: SelectChangeEvent) => setLlmModel(e.target.value)}
            >
              {llmModels.map((m) => (
                <MenuItem key={m.name} value={m.name}>
                  {m.name}
                  {m.details?.parameter_size && (
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
              {llmModels.length === 0 && (
                <MenuItem value={llmModel} disabled>
                  {llmModel ||
                    "No models — pull one with ollama pull phi3:mini"}
                </MenuItem>
              )}
            </Select>
          </FormControl>

          <Box
            sx={{
              display: "flex",
              flexWrap: "wrap",
              gap: 1,
              alignItems: "center",
            }}
          >
            <Typography variant="body2" color="text.secondary">
              Tiny model preset:
            </Typography>
            {TINY_MODELS.map((p) => (
              <Chip
                key={p.value}
                label={p.label}
                onClick={() => setLlmModel(p.value)}
                variant={llmModel === p.value ? "filled" : "outlined"}
                size="small"
              />
            ))}
          </Box>

          <FormControl fullWidth size="small">
            <InputLabel>Embedding model (RAG)</InputLabel>
            <Select
              value={embedSelectValue}
              label="Embedding model (RAG)"
              onChange={(e: SelectChangeEvent) => setEmbedModel(e.target.value)}
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
              min={256}
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
          <Button variant="contained" onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
          <Button variant="outlined" onClick={handleReset} disabled={!config}>
            Reset to saved
          </Button>
        </Box>
      </Box>
    </Box>
  );
}
