import { useState } from "react";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import { api } from "../api/client";
import type { ParsedJob } from "../api/types";
import { formatParsedSalary } from "../utils/job";

interface Props {
  onJobAdded: () => void;
}

export function AddJobForm({ onJobAdded }: Props) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ParsedJob | null>(null);
  const [duplicate, setDuplicate] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const handleParse = async () => {
    if (!url.trim()) return;
    setLoading(true);
    setError(null);
    setPreview(null);
    setDuplicate(null);

    try {
      const dupCheck = await api.checkDuplicate(url.trim());
      if (dupCheck.is_duplicate) {
        setDuplicate(
          `Already tracked: "${dupCheck.existing_job?.title}" at ${dupCheck.existing_job?.company}`,
        );
        setLoading(false);
        return;
      }
      const parsed = await api.parseUrl(url.trim());
      setPreview(parsed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to parse URL");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!preview) return;
    setSaving(true);
    setError(null);
    try {
      await api.createJob(preview);
      setPreview(null);
      setUrl("");
      onJobAdded();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
      <Box sx={{ display: "flex", gap: 1 }}>
        <TextField
          fullWidth
          size="small"
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleParse()}
          placeholder="Paste justjoin.it or nofluffjobs.com URL..."
          label="Job URL"
        />
        <Button
          variant="contained"
          onClick={handleParse}
          disabled={loading || !url.trim()}
        >
          {loading ? "Parsing..." : "Parse"}
        </Button>
      </Box>

      {error && <Alert severity="error">{error}</Alert>}
      {duplicate && (
        <Alert severity="warning">Duplicate detected: {duplicate}</Alert>
      )}

      {preview && (
        <Paper variant="outlined" sx={{ p: 2, borderColor: "divider" }}>
          <Box
            sx={{
              display: "flex",
              alignItems: "flex-start",
              justifyContent: "space-between",
              mb: 2,
            }}
          >
            <Box>
              <Typography variant="subtitle1" fontWeight={600}>
                {preview.title}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {preview.company} ·{" "}
                {preview.location.join(", ") || "No location"}
              </Typography>
            </Box>
            <Chip label={preview.source} size="small" variant="outlined" />
          </Box>

          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: "repeat(2, 1fr)",
              gap: 2,
              mb: 2,
            }}
          >
            <Box>
              <Typography variant="caption" color="text.secondary">
                Salary
              </Typography>
              <Typography variant="body2">
                {formatParsedSalary(preview.salary)}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Seniority
              </Typography>
              <Typography variant="body2">
                {preview.seniority || "N/A"}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Work Type
              </Typography>
              <Typography variant="body2">
                {preview.work_type || "N/A"}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Contract
              </Typography>
              <Typography variant="body2">
                {preview.employment_types.join(", ") || "N/A"}
              </Typography>
            </Box>
          </Box>

          {preview.skills_required.length > 0 && (
            <Box sx={{ mb: 1 }}>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ textTransform: "uppercase" }}
              >
                Required Skills
              </Typography>
              <Box
                sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.5 }}
              >
                {preview.skills_required.map((s) => (
                  <Chip
                    key={s}
                    label={s}
                    size="small"
                    color="primary"
                    variant="outlined"
                    sx={{ height: 22, fontSize: 11 }}
                  />
                ))}
              </Box>
            </Box>
          )}

          {preview.skills_nice_to_have.length > 0 && (
            <Box sx={{ mb: 2 }}>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ textTransform: "uppercase" }}
              >
                Nice to Have
              </Typography>
              <Box
                sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.5 }}
              >
                {preview.skills_nice_to_have.map((s) => (
                  <Chip
                    key={s}
                    label={s}
                    size="small"
                    variant="outlined"
                    sx={{ height: 22, fontSize: 11 }}
                  />
                ))}
              </Box>
            </Box>
          )}

          <Box sx={{ display: "flex", gap: 1, pt: 1 }}>
            <Button
              variant="contained"
              color="success"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? "Saving..." : "Save & Track"}
            </Button>
            <Button
              variant="outlined"
              onClick={() => {
                setPreview(null);
                setUrl("");
              }}
            >
              Discard
            </Button>
          </Box>
        </Paper>
      )}
    </Box>
  );
}
