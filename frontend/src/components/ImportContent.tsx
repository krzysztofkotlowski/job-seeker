import { useCallback, useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import LinearProgress from "@mui/material/LinearProgress";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Checkbox from "@mui/material/Checkbox";
import Collapse from "@mui/material/Collapse";
import FormControlLabel from "@mui/material/FormControlLabel";
import Tooltip from "@mui/material/Tooltip";
import { api } from "../api/client";
import type {
  EmbeddingStatusResponse,
  ImportStatus,
  ImportTask,
  ImportTaskStatus,
} from "../api/types";

const STATUS_LABELS: Record<ImportTaskStatus, string> = {
  idle: "Ready",
  collecting: "Collecting URLs...",
  running: "Importing...",
  done: "Completed",
  error: "Error (resumable)",
  cancelled: "Cancelled (resumable)",
};

const STATUS_CHIP_COLOR: Record<
  ImportTaskStatus,
  "default" | "warning" | "primary" | "success" | "error"
> = {
  idle: "default",
  collecting: "warning",
  running: "primary",
  done: "success",
  error: "error",
  cancelled: "warning",
};

const SOURCE_STYLE: Record<
  string,
  { color: "success" | "primary"; label: string }
> = {
  "justjoin.it": { color: "success", label: "JustJoin.it" },
  "nofluffjobs.com": { color: "primary", label: "NoFluffJobs" },
};

function TaskCard({
  task,
  onStart,
}: {
  task: ImportTask;
  onStart: () => void;
}) {
  const style = SOURCE_STYLE[task.source] ?? SOURCE_STYLE["justjoin.it"];
  const pct =
    task.total > 0 ? Math.round((task.processed / task.total) * 100) : 0;
  const isActive = task.status === "collecting" || task.status === "running";
  const buttonLabel =
    task.status === "error" || task.status === "cancelled"
      ? "Resume"
      : task.status === "done"
        ? "Re-import"
        : "Import";

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          mb: 1.5,
        }}
      >
        <Typography variant="subtitle1" fontWeight={600}>
          {style.label}
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Chip
            label={STATUS_LABELS[task.status]}
            size="small"
            color={STATUS_CHIP_COLOR[task.status]}
          />
          {!isActive && (
            <Button size="small" variant="outlined" onClick={onStart}>
              {buttonLabel}
            </Button>
          )}
        </Box>
      </Box>

      {task.status !== "idle" && (
        <Box sx={{ mb: 2 }}>
          <LinearProgress
            variant="determinate"
            value={Math.max(pct, 1)}
            color={task.status === "error" ? "error" : style.color}
            sx={{ height: 8, borderRadius: 4, mb: 0.5 }}
          />
          <Box sx={{ display: "flex", justifyContent: "space-between" }}>
            <Typography variant="caption" color="text.secondary">
              {task.processed.toLocaleString()} / {task.total.toLocaleString()}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {pct}%
            </Typography>
          </Box>
        </Box>
      )}

      {task.status !== "idle" && (
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr 1fr 1fr",
            gap: 2,
            textAlign: "center",
          }}
        >
          <StatBox label="Found" value={task.total} />
          <StatBox
            label="Imported"
            value={task.imported}
            color="success.main"
          />
          <StatBox label="Skipped" value={task.skipped} />
          <StatBox
            label="Errors"
            value={task.errors}
            color={task.errors > 0 ? "error.main" : undefined}
          />
        </Box>
      )}

      <Collapse in={task.error_log.length > 0}>
        <Box sx={{ mt: 1.5 }}>
          <Typography
            variant="caption"
            color="error"
            sx={{ cursor: "pointer" }}
          >
            {task.error_log.length} error(s)
          </Typography>
          <Box
            sx={{
              mt: 0.5,
              maxHeight: 120,
              overflow: "auto",
              bgcolor: "background.paper",
              p: 1,
              borderRadius: 1,
              fontFamily: "monospace",
              fontSize: 11,
            }}
          >
            {task.error_log.map((e, i) => (
              <Box
                key={i}
                sx={{
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {e}
              </Box>
            ))}
          </Box>
        </Box>
      </Collapse>

      {(task.status === "error" || task.status === "cancelled") &&
        task.pending > 0 && (
          <Alert severity="warning" sx={{ mt: 1.5 }}>
            {task.pending.toLocaleString()} offers remaining — click "Resume" to
            continue.
          </Alert>
        )}
    </Paper>
  );
}

function StatBox({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color?: string;
}) {
  return (
    <Box>
      <Typography
        variant="h6"
        fontWeight={700}
        sx={{ color: color ?? "text.primary" }}
      >
        {value.toLocaleString()}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
    </Box>
  );
}

export function ImportContent() {
  const [status, setStatus] = useState<ImportStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [embeddingStatus, setEmbeddingStatus] =
    useState<EmbeddingStatusResponse | null>(null);
  const [embeddingActionLoading, setEmbeddingActionLoading] = useState(false);
  const [embeddingError, setEmbeddingError] = useState<string | null>(null);
  const [embeddingUniqueOnly, setEmbeddingUniqueOnly] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const autoResumeDoneRef = useRef(false);
  const embeddingChoiceInitializedRef = useRef(false);

  const fetchStatus = useCallback(async () => {
    try {
      setStatus(await api.importStatus());
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const fetchEmbeddingStatus = useCallback(async () => {
    try {
      const s = await api.embeddingStatus();
      setEmbeddingStatus(s);
      if (!embeddingChoiceInitializedRef.current) {
        const rememberedChoice =
          s.run?.unique_only ?? s.active_run?.unique_only ?? false;
        setEmbeddingUniqueOnly(Boolean(rememberedChoice));
        embeddingChoiceInitializedRef.current = true;
      }
    } catch {
      setEmbeddingStatus({
        available: false,
        current_db_total: 0,
        run: null,
        active_run: null,
        active_index_name: null,
        active_indexed_documents: 0,
        current_config_matches_active: false,
        reindex_required: true,
        legacy_indices: [],
      });
    }
  }, []);

  useEffect(() => {
    fetchEmbeddingStatus();
  }, [fetchEmbeddingStatus]);

  useEffect(() => {
    const runStatus = embeddingStatus?.run?.status;
    const isActive = runStatus === "queued" || runStatus === "running";
    if (!isActive) return;
    const id = setInterval(fetchEmbeddingStatus, 2000);
    return () => clearInterval(id);
  }, [embeddingStatus?.run?.status, fetchEmbeddingStatus]);

  useEffect(() => {
    if (!status || autoResumeDoneRef.current || status.running) return;
    const resumable = status.tasks.some(
      (t) =>
        (t.status === "error" || t.status === "cancelled") &&
        (t.pending ?? 0) > 0,
    );
    if (!resumable) return;
    autoResumeDoneRef.current = true;
    setStarting(true);
    setError(null);
    setStatus((prev) =>
      prev
        ? {
            ...prev,
            running: true,
            tasks: prev.tasks.map((t) =>
              t.status === "error" || t.status === "cancelled"
                ? { ...t, status: "collecting" as const }
                : t,
            ),
          }
        : prev,
    );
    api
      .importStart()
      .then(() => {
        if (!intervalRef.current)
          intervalRef.current = setInterval(fetchStatus, 2000);
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Auto-resume failed"),
      )
      .finally(() => setStarting(false));
  }, [status, fetchStatus]);

  useEffect(() => {
    const isActive =
      status?.running ||
      status?.tasks.some(
        (t) => t.status === "collecting" || t.status === "running",
      );
    if (isActive) {
      if (!intervalRef.current)
        intervalRef.current = setInterval(fetchStatus, 2000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [status, fetchStatus]);

  const handleStartAll = async () => {
    setStarting(true);
    setError(null);
    setStatus((prev) =>
      prev
        ? {
            ...prev,
            running: true,
            tasks: prev.tasks.map((t) =>
              t.status === "idle" ||
              t.status === "error" ||
              t.status === "cancelled"
                ? { ...t, status: "collecting" }
                : t,
            ),
          }
        : prev,
    );
    try {
      await api.importStart();
      if (!intervalRef.current)
        intervalRef.current = setInterval(fetchStatus, 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start import");
    } finally {
      setStarting(false);
    }
  };

  const handleStartSource = async (source: string) => {
    setError(null);
    setStatus((prev) =>
      prev
        ? {
            ...prev,
            running: true,
            tasks: prev.tasks.map((t) =>
              t.source === source
                ? {
                    ...t,
                    status:
                      t.status === "done"
                        ? "collecting"
                        : t.status === "idle" ||
                            t.status === "error" ||
                            t.status === "cancelled"
                          ? "collecting"
                          : t.status,
                  }
                : t,
            ),
          }
        : prev,
    );
    try {
      await api.importStartSource(source);
      if (!intervalRef.current)
        intervalRef.current = setInterval(fetchStatus, 2000);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : `Failed to start ${source} import`,
      );
    }
  };

  const handleCancel = async () => {
    try {
      await api.importCancel();
      setTimeout(fetchStatus, 500);
    } catch {
      /* ignore */
    }
  };

  const handleSyncEmbeddings = useCallback(
    async (mode: "full" | "incremental") => {
      const uniqueOnly = embeddingUniqueOnly;
      setEmbeddingActionLoading(true);
      setEmbeddingError(null);
      try {
        const run = await api.syncEmbeddings({
          mode,
          unique_only: uniqueOnly,
        });
        setEmbeddingStatus((prev) =>
          prev
            ? { ...prev, run, current_db_total: run.db_total_snapshot }
            : {
                available: true,
                current_db_total: run.db_total_snapshot,
                run,
                active_run: null,
                active_index_name: null,
                active_indexed_documents: 0,
                current_config_matches_active: false,
                reindex_required: mode !== "full",
                legacy_indices: [],
              },
        );
        await fetchEmbeddingStatus();
      } catch (e) {
        setEmbeddingError(
          e instanceof Error ? e.message : "Embedding sync failed",
        );
      } finally {
        setEmbeddingActionLoading(false);
      }
    },
    [embeddingUniqueOnly, fetchEmbeddingStatus],
  );

  const isRunning = status?.running ?? false;
  const currentRun = embeddingStatus?.run;
  const activeRun = embeddingStatus?.active_run;
  const isEmbeddingRunActive =
    currentRun?.status === "queued" || currentRun?.status === "running";
  const progressIndexed = currentRun?.processed ?? 0;
  const progressTotal = currentRun?.target_total ?? 0;
  const progressPct =
    progressTotal > 0 ? Math.round((progressIndexed / progressTotal) * 100) : 0;
  const dbTotal = embeddingStatus?.current_db_total ?? 0;
  const selectionTotal = currentRun?.selection_total ?? activeRun?.selection_total ?? 0;
  const selectedUniqueOnly =
    currentRun?.unique_only ?? activeRun?.unique_only ?? false;
  const activeIndexedDocuments = embeddingStatus?.active_indexed_documents ?? 0;
  const activeChoice = activeRun?.unique_only;
  const incrementalDisabled =
    embeddingActionLoading ||
    isEmbeddingRunActive ||
    !embeddingStatus?.available ||
    !activeRun ||
    Boolean(embeddingStatus?.reindex_required) ||
    (typeof activeChoice === "boolean" && activeChoice !== embeddingUniqueOnly);

  useEffect(() => {
    if (!isEmbeddingRunActive) return;
    if (typeof currentRun?.unique_only !== "boolean") return;
    setEmbeddingUniqueOnly(currentRun.unique_only);
  }, [currentRun?.id, currentRun?.unique_only, isEmbeddingRunActive]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Paper sx={{ p: 3 }}>
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            mb: 3,
          }}
        >
          <Box>
            <Typography variant="h6" fontWeight={600}>
              Bulk Import
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Import all job offers from JustJoin.it and NoFluffJobs. Progress
              is saved automatically.
            </Typography>
          </Box>
          <Box sx={{ display: "flex", gap: 1 }}>
            {isRunning ? (
              <Button variant="contained" color="error" onClick={handleCancel}>
                Cancel
              </Button>
            ) : (
              <Button
                variant="contained"
                onClick={handleStartAll}
                disabled={starting}
              >
                {starting ? "Starting..." : "Import All"}
              </Button>
            )}
          </Box>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {status?.tasks.map((task) => (
            <TaskCard
              key={task.source}
              task={task}
              onStart={() => handleStartSource(task.source)}
            />
          ))}
        </Box>
      </Paper>

      <Paper sx={{ p: 3 }}>
        <Box sx={{ mb: 2 }}>
          <Typography variant="h6" fontWeight={600}>
            Vector Index (RAG)
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Index job offers for semantic search. Enables AI resume summaries to
            find relevant jobs by meaning, not just keywords. Run after
            importing jobs. May take several minutes for large datasets.
          </Typography>
        </Box>
        {embeddingStatus?.available && (
          <Box sx={{ mb: 2 }}>
            <Box
              sx={{
                display: "flex",
                flexWrap: "wrap",
                gap: 2,
                alignItems: "center",
                mb: 1,
              }}
            >
              <Tooltip title="Index only jobs not yet in RAG. Fast for new imports.">
                <span>
                  <Button
                    variant="contained"
                    color="secondary"
                    size="medium"
                    onClick={() => handleSyncEmbeddings("incremental")}
                    disabled={incrementalDisabled}
                    sx={{ minWidth: 160, fontWeight: 600 }}
                  >
                    {isEmbeddingRunActive
                      ? "Syncing..."
                      : "Add missing jobs"}
                  </Button>
                </span>
              </Tooltip>
              <Tooltip title="Clear index and rebuild from scratch. Use after bulk changes or provider switch.">
                <span>
                  <Button
                    variant="outlined"
                    color="secondary"
                    size="medium"
                    onClick={() => handleSyncEmbeddings("full")}
                    disabled={embeddingActionLoading || isEmbeddingRunActive}
                    sx={{ minWidth: 140 }}
                  >
                    Re-index all
                  </Button>
                </span>
              </Tooltip>
            </Box>
            <FormControlLabel
              control={
                <Checkbox
                  size="small"
                  checked={embeddingUniqueOnly}
                  disabled={embeddingActionLoading || isEmbeddingRunActive}
                  onChange={(e) => setEmbeddingUniqueOnly(e.target.checked)}
                />
              }
              label={
                <Typography variant="body2" color="text.secondary">
                  Index only unique jobs by company + title (same as Hide
                  duplicates in Jobs view)
                </Typography>
              }
            />
          </Box>
        )}
        {embeddingError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {embeddingError}
          </Alert>
        )}
        {embeddingStatus?.available &&
          embeddingStatus?.reindex_required &&
          !isEmbeddingRunActive && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              Incremental indexing is disabled because the active vector index
              does not match the current embedding configuration. Run a full
              rebuild.
            </Alert>
          )}
        {embeddingStatus?.available &&
          activeRun &&
          !embeddingStatus?.current_config_matches_active && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Recommendations are currently using an older active index built
              with {activeRun.embed_model} ({activeRun.embed_dims} dims). They
              will switch only after a full rebuild completes.
            </Alert>
          )}
        {embeddingStatus?.available && (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
            <Typography variant="body2" color="text.secondary">
              DB jobs: {dbTotal.toLocaleString()}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Selected scope: {selectionTotal.toLocaleString()}
              {selectedUniqueOnly ? " (duplicates hidden)" : " (with duplicates)"}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Current run: {progressIndexed.toLocaleString()} /{" "}
              {progressTotal.toLocaleString()}
              {currentRun ? ` (${currentRun.status})` : " (idle)"}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Active vector index: {activeIndexedDocuments.toLocaleString()}
              {embeddingStatus?.active_index_name
                ? ` docs (${embeddingStatus.active_index_name})`
                : " docs"}
            </Typography>
            {(embeddingStatus?.legacy_indices?.length ?? 0) > 0 && (
              <Typography variant="caption" color="text.secondary">
                Legacy Elasticsearch indices still present:{" "}
                {embeddingStatus?.legacy_indices?.length ?? 0}
              </Typography>
            )}
          </Box>
        )}
        {isEmbeddingRunActive && (
          <Box sx={{ mt: 2 }}>
            <LinearProgress
              variant="determinate"
              value={progressPct}
              sx={{ height: 8, borderRadius: 4, mb: 0.5 }}
            />
            <Typography variant="caption" color="text.secondary">
              {progressIndexed.toLocaleString()} /{" "}
              {progressTotal.toLocaleString()}
            </Typography>
          </Box>
        )}
        {!embeddingStatus?.available && embeddingStatus !== null && (
          <Alert severity="info" sx={{ mt: 1 }}>
            Elasticsearch is not available. RAG features are disabled.
          </Alert>
        )}
      </Paper>
    </Box>
  );
}
