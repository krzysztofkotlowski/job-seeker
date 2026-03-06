import { useCallback, useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import LinearProgress from "@mui/material/LinearProgress";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import { api } from "../api/client";
import type { ImportStatus, ImportTask, ImportTaskStatus } from "../api/types";

const STATUS_LABELS: Record<ImportTaskStatus, string> = {
  idle: "Ready",
  collecting: "Collecting URLs...",
  running: "Importing...",
  done: "Completed",
  error: "Error (resumable)",
  cancelled: "Cancelled (resumable)",
};

const STATUS_CHIP_COLOR: Record<ImportTaskStatus, "default" | "warning" | "primary" | "success" | "error"> = {
  idle: "default",
  collecting: "warning",
  running: "primary",
  done: "success",
  error: "error",
  cancelled: "warning",
};

const SOURCE_STYLE: Record<string, { color: "success" | "primary"; label: string }> = {
  "justjoin.it": { color: "success", label: "JustJoin.it" },
  "nofluffjobs.com": { color: "primary", label: "NoFluffJobs" },
};

type EmbeddingStatus = { available: boolean; indexed: number; total: number; syncing?: boolean } | null;

export function ImportPage() {
  const [status, setStatus] = useState<ImportStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [embeddingStatus, setEmbeddingStatus] = useState<EmbeddingStatus>(null);
  const [embeddingSyncing, setEmbeddingSyncing] = useState(false);
  const [embeddingProgress, setEmbeddingProgress] = useState({ indexed: 0, total: 0 });
  const [embeddingError, setEmbeddingError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const autoResumeDoneRef = useRef(false);

  const fetchStatus = useCallback(async () => {
    try {
      setStatus(await api.importStatus());
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const fetchEmbeddingStatus = useCallback(async () => {
    try {
      const s = await api.embeddingStatus();
      setEmbeddingStatus(s);
    } catch {
      setEmbeddingStatus({ available: false, indexed: 0, total: 0, syncing: false });
    }
  }, []);

  useEffect(() => {
    fetchEmbeddingStatus();
  }, [fetchEmbeddingStatus]);

  // Poll embedding status when sync might be in progress (startup or indexed < total)
  useEffect(() => {
    if (!embeddingStatus?.available) return;
    const mightBeSyncing = embeddingStatus.syncing || (embeddingStatus.total > 0 && embeddingStatus.indexed < embeddingStatus.total);
    if (!mightBeSyncing) return;
    const id = setInterval(fetchEmbeddingStatus, 3000);
    return () => clearInterval(id);
  }, [embeddingStatus, fetchEmbeddingStatus]);

  // If any task is resumable (error/cancelled with pending), auto-start import once
  useEffect(() => {
    if (!status || autoResumeDoneRef.current || status.running) return;
    const resumable = status.tasks.some(
      (t) => (t.status === "error" || t.status === "cancelled") && (t.pending ?? 0) > 0,
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
        if (!intervalRef.current) intervalRef.current = setInterval(fetchStatus, 2000);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Auto-resume failed"))
      .finally(() => setStarting(false));
  }, [status, fetchStatus]);

  useEffect(() => {
    const isActive =
      status?.running ||
      status?.tasks.some((t) => t.status === "collecting" || t.status === "running");

    if (isActive) {
      if (!intervalRef.current) intervalRef.current = setInterval(fetchStatus, 2000);
    } else {
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
    }
    return () => { if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; } };
  }, [status, fetchStatus]);

  const handleStartAll = async () => {
    setStarting(true);
    setError(null);
    // Optimistically mark tasks as collecting so the user immediately sees progress starting.
    setStatus((prev) =>
      prev
        ? {
            ...prev,
            running: true,
            tasks: prev.tasks.map((t) =>
              t.status === "idle" || t.status === "error" || t.status === "cancelled"
                ? { ...t, status: "collecting" }
                : t,
            ),
          }
        : prev,
    );
    try {
      await api.importStart();
      if (!intervalRef.current) intervalRef.current = setInterval(fetchStatus, 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start import");
    } finally {
      setStarting(false);
    }
  };

  const handleStartSource = async (source: string) => {
    setError(null);
    // Optimistically update this source's task so the button/label change immediately.
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
                        ? "collecting" // re-import behaves like a fresh run
                        : t.status === "idle" || t.status === "error" || t.status === "cancelled"
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
      if (!intervalRef.current) intervalRef.current = setInterval(fetchStatus, 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to start ${source} import`);
    }
  };

  const handleCancel = async () => {
    try {
      await api.importCancel();
      setTimeout(fetchStatus, 500);
    } catch { /* ignore */ }
  };

  const handleSyncEmbeddings = async () => {
    setEmbeddingSyncing(true);
    setEmbeddingError(null);
    setEmbeddingProgress({ indexed: 0, total: 0 });
    try {
      await api.syncEmbeddingsStream(
        (indexed, total) => setEmbeddingProgress({ indexed, total }),
      );
      await fetchEmbeddingStatus();
    } catch (e) {
      setEmbeddingError(e instanceof Error ? e.message : "Embedding sync failed");
    } finally {
      setEmbeddingSyncing(false);
    }
  };

  const isRunning = status?.running ?? false;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Paper sx={{ p: 3 }}>
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 3 }}>
          <Box>
            <Typography variant="h6" fontWeight={600}>Bulk Import</Typography>
            <Typography variant="body2" color="text.secondary">
              Import all job offers from JustJoin.it and NoFluffJobs. Progress is saved automatically.
            </Typography>
          </Box>
          <Box sx={{ display: "flex", gap: 1 }}>
            {isRunning ? (
              <Button variant="contained" color="error" onClick={handleCancel}>Cancel</Button>
            ) : (
              <Button variant="contained" onClick={handleStartAll} disabled={starting}>
                {starting ? "Starting..." : "Import All"}
              </Button>
            )}
          </Box>
        </Box>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {status?.tasks.map((task) => (
            <TaskCard key={task.source} task={task} onStart={() => handleStartSource(task.source)} />
          ))}
        </Box>
      </Paper>

      <Paper sx={{ p: 3 }}>
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 2 }}>
          <Box>
            <Typography variant="h6" fontWeight={600}>Vector Index (RAG)</Typography>
            <Typography variant="body2" color="text.secondary">
              Index job offers for semantic search. Enables AI resume summaries to find relevant jobs by meaning, not
              just keywords. Run after importing jobs. May take several minutes for large datasets.
            </Typography>
          </Box>
          {embeddingStatus?.available && (
            <Button
              variant="contained"
              color="secondary"
              size="medium"
              onClick={handleSyncEmbeddings}
              disabled={embeddingSyncing || embeddingStatus.syncing}
              sx={{ minWidth: 140, fontWeight: 600 }}
            >
              {embeddingSyncing || embeddingStatus.syncing ? "Syncing..." : "Index for RAG"}
            </Button>
          )}
        </Box>
        {embeddingError && <Alert severity="error" sx={{ mb: 2 }}>{embeddingError}</Alert>}
        {embeddingStatus?.available && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <Typography variant="body2" color="text.secondary">
              {embeddingStatus.indexed.toLocaleString()} / {embeddingStatus.total.toLocaleString()} indexed
            </Typography>
          </Box>
        )}
        {(embeddingSyncing || embeddingStatus?.syncing) && (
          <Box sx={{ mt: 2 }}>
            <LinearProgress
              variant="determinate"
              value={
                (embeddingSyncing && embeddingProgress.total > 0)
                  ? Math.round((embeddingProgress.indexed / embeddingProgress.total) * 100)
                  : embeddingStatus && embeddingStatus.total > 0
                    ? Math.round((embeddingStatus.indexed / embeddingStatus.total) * 100)
                    : 0
              }
              sx={{ height: 8, borderRadius: 4, mb: 0.5 }}
            />
            <Typography variant="caption" color="text.secondary">
              {(embeddingSyncing && embeddingProgress.total > 0 ? embeddingProgress.indexed : embeddingStatus?.indexed ?? 0).toLocaleString()} / {(embeddingSyncing && embeddingProgress.total > 0 ? embeddingProgress.total : embeddingStatus?.total ?? 0).toLocaleString()}
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

function TaskCard({ task, onStart }: { task: ImportTask; onStart: () => void }) {
  const style = SOURCE_STYLE[task.source] ?? SOURCE_STYLE["justjoin.it"];
  const pct = task.total > 0 ? Math.round((task.processed / task.total) * 100) : 0;
  const isActive = task.status === "collecting" || task.status === "running";

  const buttonLabel =
    task.status === "error" || task.status === "cancelled" ? "Resume"
    : task.status === "done" ? "Re-import"
    : "Import";

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1.5 }}>
        <Typography variant="subtitle1" fontWeight={600}>{style.label}</Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Chip label={STATUS_LABELS[task.status]} size="small" color={STATUS_CHIP_COLOR[task.status]} />
          {!isActive && (
            <Button size="small" variant="outlined" onClick={onStart}>{buttonLabel}</Button>
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
            <Typography variant="caption" color="text.secondary">{pct}%</Typography>
          </Box>
        </Box>
      )}

      {task.status !== "idle" && (
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 2, textAlign: "center" }}>
          <StatBox label="Found" value={task.total} />
          <StatBox label="Imported" value={task.imported} color="success.main" />
          <StatBox label="Skipped" value={task.skipped} />
          <StatBox label="Errors" value={task.errors} color={task.errors > 0 ? "error.main" : undefined} />
        </Box>
      )}

      <Collapse in={task.error_log.length > 0}>
        <Box sx={{ mt: 1.5 }}>
          <Typography variant="caption" color="error" sx={{ cursor: "pointer" }}>
            {task.error_log.length} error(s)
          </Typography>
          <Box sx={{ mt: 0.5, maxHeight: 120, overflow: "auto", bgcolor: "background.paper", p: 1, borderRadius: 1, fontFamily: "monospace", fontSize: 11 }}>
            {task.error_log.map((e, i) => (
              <Box key={i} sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e}</Box>
            ))}
          </Box>
        </Box>
      </Collapse>

      {(task.status === "error" || task.status === "cancelled") && task.pending > 0 && (
        <Alert severity="warning" sx={{ mt: 1.5 }}>
          {task.pending.toLocaleString()} offers remaining -- click "Resume" to continue.
        </Alert>
      )}
    </Paper>
  );
}

function StatBox({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <Box>
      <Typography variant="h6" fontWeight={700} sx={{ color: color ?? "text.primary" }}>
        {value.toLocaleString()}
      </Typography>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
    </Box>
  );
}
