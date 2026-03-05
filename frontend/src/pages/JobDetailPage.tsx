import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import TextField from "@mui/material/TextField";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import BookmarkIcon from "@mui/icons-material/Bookmark";
import BookmarkBorderIcon from "@mui/icons-material/BookmarkBorder";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import { api } from "../api/client";
import type { Job, JobStatus, DetectedSkill } from "../api/types";

const STATUSES: JobStatus[] = ["new", "seen", "applied", "interview", "offer", "rejected"];

const STATUS_COLOR: Record<string, "default" | "primary" | "warning" | "success" | "error" | "info"> = {
  new: "primary",
  seen: "default",
  applied: "warning",
  interview: "info",
  offer: "success",
  rejected: "error",
};

export function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [detectedSkills, setDetectedSkills] = useState<DetectedSkill[]>([]);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api.getJob(id).then((j) => { setJob(j); setNotes(j.notes); })
      .catch(() => navigate("/jobs"))
      .finally(() => setLoading(false));
    api.detectedSkills(id).then(setDetectedSkills).catch(() => {});
  }, [id, navigate]);

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }
  if (!job) return null;

  const handleStatusChange = async (status: JobStatus) => {
    setSaving(true);
    try { setJob(await api.updateJob(job.id, { status })); }
    finally { setSaving(false); }
  };

  const handleSaveNotes = async () => {
    setSaving(true);
    try { setJob(await api.updateJob(job.id, { notes })); }
    finally { setSaving(false); }
  };

  const handleToggleReposted = async () => {
    setSaving(true);
    try { setJob(await api.updateJob(job.id, { is_reposted: !job.is_reposted })); }
    finally { setSaving(false); }
  };

  const handleToggleSaved = async () => {
    setSaving(true);
    try { setJob(await api.updateJob(job.id, { saved: !job.saved })); }
    finally { setSaving(false); }
  };

  const handleDelete = async () => {
    if (!confirm("Remove this job from tracking?")) return;
    setDeleting(true);
    try { await api.deleteJob(job.id); navigate("/jobs"); }
    finally { setDeleting(false); }
  };

  const sal = formatSalaryLines(job);

  return (
    <Paper sx={{ overflow: "hidden" }}>
      {/* Header */}
      <Box sx={{ p: 3, borderBottom: 1, borderColor: "divider" }}>
        <Box sx={{ display: "flex", gap: 1, mb: 2 }}>
        <Button
          startIcon={<ArrowBackIcon />}
          size="small"
          onClick={() => navigate(-1)}
        >
          Back to list
        </Button>
        {job.status !== "seen" && (
          <Button
            startIcon={<VisibilityOffIcon />}
            size="small"
            variant="outlined"
            color="inherit"
            onClick={async () => {
              try { await api.updateJob(job.id, { status: "seen" }); } catch {}
              navigate(-1);
            }}
            disabled={saving}
          >
            Seen &amp; Go Back
          </Button>
        )}
        <Button
          startIcon={job.saved ? <BookmarkIcon /> : <BookmarkBorderIcon />}
          size="small"
          variant="outlined"
          color={job.saved ? "primary" : "inherit"}
          onClick={handleToggleSaved}
          disabled={saving}
        >
          {job.saved ? "Saved" : "Save for later"}
        </Button>
        </Box>

        <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 2 }}>
          <Box>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Typography variant="h5" fontWeight={700}>{job.title}</Typography>
              {job.saved && <Chip label="Saved" size="small" color="primary" />}
              {job.is_reposted && <Chip label="Reposted" size="small" color="warning" />}
            </Box>
            <Typography variant="subtitle1" color="text.secondary">{job.company}</Typography>
          </Box>
          <Chip
            label={job.status.charAt(0).toUpperCase() + job.status.slice(1)}
            color={STATUS_COLOR[job.status] ?? "default"}
          />
        </Box>
      </Box>

      <Box sx={{ p: 3, display: "flex", flexDirection: "column", gap: 3 }}>
        {/* Reposted info */}
        {job.is_reposted && job.original_job_id && (
          <Alert severity="warning" sx={{ mb: 1.5 }}>
            This is a reposted offer.{" "}
            <Link to={`/jobs/${job.original_job_id}`} style={{ fontWeight: 600 }}>View original posting</Link>
          </Alert>
        )}

        {/* Cross-source listings */}
        {job.alternate_listings && job.alternate_listings.length > 0 && (
          <Alert severity="info" sx={{ mb: 1.5 }}>
            Also listed on:&nbsp;
            {job.alternate_listings.map((alt, idx) => (
              <Button
                key={alt.id}
                size="small"
                href={alt.url}
                target="_blank"
                rel="noopener noreferrer"
                sx={{ ml: idx === 0 ? 0 : 1 }}
              >
                {alt.source}
              </Button>
            ))}
          </Alert>
        )}

        {/* Status Controls */}
        <Box>
          <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 1 }}>Status</Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
            {STATUSES.map((s) => (
              <Button
                key={s}
                size="small"
                variant={job.status === s ? "contained" : "outlined"}
                onClick={() => handleStatusChange(s)}
                disabled={saving || job.status === s}
              >
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </Button>
            ))}
          </Box>
        </Box>

        {/* Info Grid */}
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", md: "1fr 1fr 1fr" }, gap: 2 }}>
          <Box>
            <Typography variant="overline" color="text.secondary">Salary</Typography>
            <Typography variant="body2" fontWeight={700} color="success.dark">{sal.plnLine}</Typography>
            {sal.hourlyLine && <Typography variant="caption" color="text.secondary">{sal.hourlyLine}</Typography>}
            {sal.originalLine && <Typography variant="caption" display="block" color="text.disabled">{sal.originalLine}</Typography>}
          </Box>
          <InfoItem label="Location" value={job.location.join(", ") || "Not specified"} />
          <InfoItem label="Seniority" value={job.seniority || "N/A"} />
          <InfoItem label="Work Type" value={job.work_type || "N/A"} />
          <InfoItem label="Contract" value={job.employment_types.join(", ") || "N/A"} />
          <InfoItem label="Category" value={job.category || "N/A"} />
          <InfoItem label="Source" value={job.source} />
          <InfoItem label="Added" value={job.date_added} />
          {job.applied_date && <InfoItem label="Applied" value={job.applied_date} />}
          {job.date_expires && <InfoItem label="Expires" value={job.date_expires} />}
        </Box>

        {/* Skills */}
        {job.skills_required.length > 0 && (
          <Box>
            <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 1 }}>Required Skills</Typography>
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
              {job.skills_required.map((s) => (
                <Chip key={s} label={s} size="small" color="primary" variant="outlined" />
              ))}
            </Box>
          </Box>
        )}

        {job.skills_nice_to_have.length > 0 && (
          <Box>
            <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 1 }}>Nice to Have</Typography>
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
              {job.skills_nice_to_have.map((s) => (
                <Chip key={s} label={s} size="small" variant="outlined" />
              ))}
            </Box>
          </Box>
        )}

        {detectedSkills.length > 0 && (
          <Box>
            <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 1 }}>
              Detected Skills
              <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                found in {detectedSkills.some(d => d.source_field === "title") ? "title & " : ""}description
              </Typography>
            </Typography>
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
              {detectedSkills.map((d) => (
                <Chip key={d.skill_name} label={d.skill_name} size="small" color="success" variant="outlined" />
              ))}
            </Box>
          </Box>
        )}

        {/* Notes */}
        <Box>
          <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 1 }}>Notes</Typography>
          <TextField
            multiline
            rows={4}
            fullWidth
            size="small"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Add personal notes about this job..."
          />
          <Button
            variant="contained"
            size="small"
            onClick={handleSaveNotes}
            disabled={saving || notes === job.notes}
            sx={{ mt: 1 }}
          >
            Save Notes
          </Button>
        </Box>

        {/* Description */}
        {job.description && (
          <Box>
            <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 1 }}>Job Description</Typography>
            <Box
              sx={{
                bgcolor: "background.paper",
                borderRadius: 2,
                p: 3,
                maxHeight: 600,
                overflow: "auto",
                fontSize: 14,
                lineHeight: 1.7,
                "& h3": { fontSize: 15, fontWeight: 700, mt: 2.5, mb: 1, color: "text.primary" },
                "& p": { my: 1, color: "text.secondary" },
                "& ul": { pl: 2.5, my: 1 },
                "& li": { mb: 0.5, color: "text.secondary" },
              }}
              dangerouslySetInnerHTML={{ __html: formatDescription(job.description) }}
            />
          </Box>
        )}

        <Divider />

        {/* Actions */}
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Box sx={{ display: "flex", gap: 1 }}>
            <Button
              size="small"
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              startIcon={<OpenInNewIcon />}
            >
              Open original listing
            </Button>
            <Button
              size="small"
              variant="outlined"
              color={job.is_reposted ? "warning" : "inherit"}
              onClick={handleToggleReposted}
              disabled={saving}
            >
              {job.is_reposted ? "Unmark Reposted" : "Mark as Reposted"}
            </Button>
          </Box>
          <Button
            size="small"
            color="error"
            startIcon={<DeleteOutlineIcon />}
            onClick={handleDelete}
            disabled={deleting}
          >
            {deleting ? "Removing..." : "Remove Job"}
          </Button>
        </Box>
      </Box>
    </Paper>
  );
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography variant="overline" color="text.secondary">{label}</Typography>
      <Typography variant="body2" fontWeight={500}>{value}</Typography>
    </Box>
  );
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatDescription(raw: string): string {
  let text = raw.replace(/\xa0/g, " ").replace(/\r\n/g, "\n").replace(/\r/g, "\n");

  // If the text has very few newlines relative to length, insert breaks
  // at sentences that run together (period/colon followed by uppercase letter)
  const newlineRatio = (text.match(/\n/g) || []).length / text.length;
  if (newlineRatio < 0.005) {
    text = text.replace(/([.!?])([A-ZŻŹĆĄŚĘŁÓŃ])/g, "$1\n\n$2");
    text = text.replace(/:([A-ZŻŹĆĄŚĘŁÓŃ])/g, ":\n$1");
  }

  const lines = text.split("\n");
  const htmlParts: string[] = [];
  let inList = false;

  const isBullet = (line: string) =>
    /^\s*[•·–—\-\*►▸▹✓✔☑]\s/.test(line) || /^\s*\d+[.)]\s/.test(line);

  const isHeader = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) return false;
    if (trimmed.length > 80) return false;
    if (/^[A-ZŻŹĆĄŚĘŁÓŃ\s&/,\-–:()]+$/.test(trimmed) && trimmed.length > 3) return true;
    if (/:\s*$/.test(trimmed) && trimmed.length < 60) return true;
    return false;
  };

  const stripBullet = (line: string) =>
    line.replace(/^\s*[•·–—\-\*►▸▹✓✔☑]\s*/, "").replace(/^\s*\d+[.)]\s*/, "").trim();

  for (const line of lines) {
    const trimmed = line.trim();

    if (!trimmed) {
      if (inList) { htmlParts.push("</ul>"); inList = false; }
      continue;
    }

    if (isBullet(trimmed)) {
      if (!inList) { htmlParts.push("<ul>"); inList = true; }
      htmlParts.push(`<li>${escapeHtml(stripBullet(trimmed))}</li>`);
      continue;
    }

    if (inList) { htmlParts.push("</ul>"); inList = false; }

    if (isHeader(trimmed)) {
      htmlParts.push(`<h3>${escapeHtml(trimmed.replace(/:\s*$/, ""))}</h3>`);
    } else {
      htmlParts.push(`<p>${escapeHtml(trimmed)}</p>`);
    }
  }

  if (inList) htmlParts.push("</ul>");

  return htmlParts.join("");
}

function formatSalaryLines(job: Job) {
  const s = job.salary;
  if (!s || (!s.min && !s.max)) return { plnLine: "Not specified", hourlyLine: null, originalLine: null };
  const fmt = (n: number | null) => (n != null ? n.toLocaleString("pl-PL", { maximumFractionDigits: 0 }) : "?");
  const cur = s.currency ?? "";
  const periodLabel = s.period === "hourly" ? "/h" : s.period === "daily" ? "/day" : "/mo";
  const contractType = s.type ? ` (${s.type})` : "";
  const originalStr = `${fmt(s.min)} - ${fmt(s.max)} ${cur}${periodLabel}${contractType}`;

  if (s.min_pln != null && s.max_pln != null) {
    const plnLine = `${fmt(s.min_pln)} - ${fmt(s.max_pln)} PLN/mo`;
    const hMin = Math.round(s.min_pln / 160);
    const hMax = Math.round(s.max_pln / 160);
    const hourlyLine = `${fmt(hMin)} - ${fmt(hMax)} PLN/h`;
    const originalLine = cur !== "PLN" || s.period !== "monthly" ? originalStr : null;
    return { plnLine, hourlyLine, originalLine };
  }
  return { plnLine: originalStr, hourlyLine: null, originalLine: null };
}
