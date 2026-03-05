import { useCallback, useEffect, useState, memo } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LabelList,
} from "recharts";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Fade from "@mui/material/Fade";
import Grow from "@mui/material/Grow";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import LinearProgress from "@mui/material/LinearProgress";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import type { SelectChangeEvent } from "@mui/material/Select";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import { api } from "../api/client";
import type { ResumeAnalyzeResult, ResumeByCategory, SkillWithWeight } from "../api/types";

const ACCEPT = ".pdf";
const ANALYZE_TIMEOUT_MS = 45000;
const SUMMARIZE_TIMEOUT_MS = 120000;

function toSkillWithWeight(x: unknown): SkillWithWeight {
  if (x && typeof x === "object" && "skill" in x && typeof (x as SkillWithWeight).skill === "string") {
    const sw = x as SkillWithWeight;
    return { skill: sw.skill, weight: typeof sw.weight === "number" ? sw.weight : 1 };
  }
  return { skill: String(x ?? ""), weight: 1 };
}

/** Normalize API response so we support both extracted_skills and legacy extracted_keywords. */
function normalizeResult(data: ResumeAnalyzeResult | null): ResumeAnalyzeResult | null {
  if (!data || typeof data !== "object") return null;
  const raw = data as unknown as Record<string, unknown>;
  const extracted =
    Array.isArray(raw.extracted_skills) ? raw.extracted_skills as string[]
    : Array.isArray(raw.extracted_keywords) ? raw.extracted_keywords as string[]
    : [];
  const byCategory = (Array.isArray(data.by_category) ? data.by_category : []).map((c: unknown) => {
    const cat = c as Record<string, unknown>;
    const matching = Array.isArray(cat.matching_skills) ? cat.matching_skills.map(toSkillWithWeight) : [];
    const toAdd = Array.isArray(cat.skills_to_add)
      ? cat.skills_to_add.map(toSkillWithWeight)
      : [
          ...(Array.isArray(cat.skills_to_add_required) ? cat.skills_to_add_required : []).map((s) => ({ skill: String(s), weight: 1 })),
          ...(Array.isArray(cat.skills_to_add_nice) ? cat.skills_to_add_nice : []).map((s) => ({ skill: String(s), weight: 1 })),
        ];
    const total = matching.reduce((a, x) => a + x.weight, 0) + toAdd.reduce((a, x) => a + x.weight, 0);
    const matchScore = total > 0 ? Math.round((matching.reduce((a, x) => a + x.weight, 0) / total) * 100) : 0;
    return {
      ...cat,
      category: cat.category ?? "",
      job_count: typeof cat.job_count === "number" ? cat.job_count : 0,
      match_score: typeof cat.match_score === "number" ? cat.match_score : matchScore,
      matching_skills: matching,
      skills_to_add: toAdd,
    } as ResumeByCategory;
  });
  return {
    extracted_skills: extracted,
    match_count: typeof data.match_count === "number" ? data.match_count : 0,
    matches: Array.isArray(data.matches) ? data.matches : [],
    by_category: byCategory,
    message: data.message,
    summary: typeof raw.summary === "string" ? raw.summary : undefined,
  };
}

/** Max chart height so all labels display. Exported for tests. */
export const CHART_MAX_HEIGHT = 1200;
const CHART_ROW_HEIGHT = 44;
const CHART_MIN_HEIGHT = 240;
const CHART_ANIMATION_DURATION = 400;

function chartHeight(itemCount: number): number {
  return Math.min(Math.max(itemCount * CHART_ROW_HEIGHT, CHART_MIN_HEIGHT), CHART_MAX_HEIGHT);
}

const MatchedSkillsChart = memo(function MatchedSkillsChart({ data }: { data: SkillWithWeight[] }) {
  if (data.length === 0) return <Typography variant="body2" color="text.secondary">None</Typography>;
  return (
    <ResponsiveContainer width="100%" height={chartHeight(data.length)}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 50 }} barCategoryGap={4} barGap={4}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 14 }} />
        <YAxis type="category" dataKey="skill" width={200} tick={{ fontSize: 14 }} />
        <Tooltip formatter={(v) => [`×${v ?? 0}`, "Occurrences"]} />
        <Bar dataKey="weight" fill="#22c55e" radius={[0, 6, 6, 0]} barSize={28} animationDuration={CHART_ANIMATION_DURATION}>
          <LabelList dataKey="weight" position="right" formatter={(v) => `×${v ?? 0}`} style={{ fontSize: 13, fill: "#166534" }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
});

const SkillsToAddChart = memo(function SkillsToAddChart({ data }: { data: SkillWithWeight[] }) {
  if (data.length === 0) return <Typography variant="body2" color="text.secondary">None</Typography>;
  return (
    <ResponsiveContainer width="100%" height={chartHeight(data.length)}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 50 }} barCategoryGap={4} barGap={4}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 14 }} />
        <YAxis type="category" dataKey="skill" width={200} tick={{ fontSize: 14 }} />
        <Tooltip formatter={(v) => [`×${v ?? 0}`, "Occurrences"]} />
        <Bar dataKey="weight" fill="#ef4444" radius={[0, 6, 6, 0]} barSize={28} animationDuration={CHART_ANIMATION_DURATION}>
          <LabelList dataKey="weight" position="right" formatter={(v) => `×${v ?? 0}`} style={{ fontSize: 13, fill: "#991b1b" }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
});

export function ResumeAnalysisPage() {
  const [result, setResult] = useState<ResumeAnalyzeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [chartsReady, setChartsReady] = useState(false);
  const safe = normalizeResult(result);

  useEffect(() => {
    api.listCategories().then(setCategories).catch(() => {});
  }, []);

  useEffect(() => {
    if (!safe) {
      setChartsReady(false);
      return;
    }
    const id = requestAnimationFrame(() => setChartsReady(true));
    return () => cancelAnimationFrame(id);
  }, [safe]);

  const handleFile = useCallback(
    async (file: File | null) => {
      if (!file) return;
      setError(null);
      setResult(null);
      setSummaryError(null);
      setLoading(true);
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), ANALYZE_TIMEOUT_MS);
      try {
        const data = await api.resumeAnalyze(file, controller.signal);
        const normalized = normalizeResult(data) ?? data;
        setResult(normalized);
        const top = (normalized?.by_category ?? []).sort((a, b) => (b.match_score ?? 0) - (a.match_score ?? 0))[0];
        setSelectedCategory(top?.category ?? "");
      } catch (e) {
        if (e instanceof Error) {
          setError(e.name === "AbortError" ? "Request timed out. Try again." : e.message);
        } else {
          setError("Upload failed");
        }
      } finally {
        clearTimeout(timeoutId);
        setLoading(false);
      }
    },
    [],
  );

  const handleSummarize = useCallback(async () => {
    if (!safe) return;
    setSummaryError(null);
    setSummaryLoading(true);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), SUMMARIZE_TIMEOUT_MS);
    try {
      // Send only data needed for prompt to avoid 413 Payload Too Large
      const topMatches = safe.matches.slice(0, 5).map((m) => ({
        job: { title: m.job?.title, company: m.job?.company },
        matched_skills: m.matched_skills,
        match_count: m.match_count,
      }));
      const topCategories = [...safe.by_category]
        .sort((a, b) => (b.match_score ?? 0) - (a.match_score ?? 0))
        .slice(0, 3)
        .map((c) => ({
          category: c.category,
          match_score: c.match_score,
          matching_skills: c.matching_skills?.slice(0, 8) ?? [],
          skills_to_add: c.skills_to_add?.slice(0, 5) ?? [],
        }));
      const { summary } = await api.resumeSummarize(
        {
          extracted_skills: safe.extracted_skills,
          matches: topMatches,
          by_category: topCategories,
        },
        controller.signal,
      );
      setResult((prev) => (prev ? { ...prev, summary } : prev));
    } catch (e) {
      if (e instanceof Error) {
        setSummaryError(e.name === "AbortError" ? "Summary timed out. Try again." : e.message);
      } else {
        setSummaryError("Summary failed");
      }
    } finally {
      clearTimeout(timeoutId);
      setSummaryLoading(false);
    }
  }, [safe]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
    e.target.value = "";
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f && f.name.toLowerCase().endsWith(".pdf")) handleFile(f);
  };

  const handleDragOver = (e: React.DragEvent) => e.preventDefault();

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" fontWeight={600} sx={{ mb: 1 }}>
          Resume analysis
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Upload your resume as a PDF. We extract keywords and skills from the text and compare them
          with our job offers to show the best matches.
        </Typography>

        <Box
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          sx={{
            border: "2px dashed",
            borderColor: "divider",
            borderRadius: 2,
            p: 4,
            textAlign: "center",
            bgcolor: "action.hover",
          }}
        >
          <input
            accept={ACCEPT}
            type="file"
            id="resume-upload"
            hidden
            onChange={handleInputChange}
            disabled={loading}
          />
          <label htmlFor="resume-upload">
            <Button
              component="span"
              variant="outlined"
              startIcon={<UploadFileIcon />}
              disabled={loading}
            >
              Choose PDF
            </Button>
          </label>
          <Typography variant="caption" display="block" sx={{ mt: 1 }} color="text.secondary">
            or drag and drop a PDF here
          </Typography>
        </Box>

        {loading && <LinearProgress sx={{ mt: 2, transition: "opacity 0.2s ease" }} />}
        {error && (
          <Alert severity="error" sx={{ mt: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
      </Paper>

      {safe && (
        <Fade in timeout={200}>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <Grow in timeout={350}>
            <Paper
              elevation={2}
              sx={{
                p: 3,
                borderLeft: "4px solid",
                borderColor: "primary.main",
                bgcolor: "action.hover",
                transition: "box-shadow 0.3s ease, transform 0.2s ease",
                "&:hover": { boxShadow: 2 },
              }}
            >
              <Typography variant="subtitle1" fontWeight={600} sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
                <AutoAwesomeIcon color="primary" fontSize="small" />
                AI Summary & Recommendations
              </Typography>
              {safe.summary ? (
                <Typography variant="body1" component="div" sx={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
                  {safe.summary}
                </Typography>
              ) : (
                <Box>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    Get personalized career advice based on your resume and job market matches.
                  </Typography>
                  <Button
                    variant="contained"
                    startIcon={<AutoAwesomeIcon />}
                    onClick={handleSummarize}
                    disabled={summaryLoading || safe.extracted_skills.length === 0}
                    sx={{ textTransform: "none", fontWeight: 600 }}
                  >
                    {summaryLoading ? "Generating..." : "Generate AI summary"}
                  </Button>
                  {summaryLoading && <LinearProgress sx={{ mt: 2, borderRadius: 1 }} />}
                  {summaryError && (
                    <Alert severity="error" sx={{ mt: 2 }} onClose={() => setSummaryError(null)}>
                      {summaryError}
                    </Alert>
                  )}
                </Box>
              )}
            </Paper>
          </Grow>

          <Grow in timeout={450}>
            <Paper sx={{ p: 3, transition: "box-shadow 0.3s ease" }}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
              Skills from your PDF (in our system) ({safe.extracted_skills.length})
            </Typography>
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mb: 3 }}>
              {safe.extracted_skills.slice(0, 80).map((k) => (
                <Chip key={k} label={k} size="small" variant="outlined" color="primary" />
              ))}
              {safe.extracted_skills.length > 80 && (
                <Chip label={`+${safe.extracted_skills.length - 80} more`} size="small" />
              )}
            </Box>

            {safe.message && (
              <Alert severity="info" sx={{ mb: 2 }}>
                {safe.message}
              </Alert>
            )}
          </Paper>
          </Grow>

          {categories.length > 0 && safe.by_category.length > 0 && chartsReady && (
          <Grow in timeout={550}>
            <Paper sx={{ p: 3, transition: "box-shadow 0.3s ease" }}>
            {(() => {
              const topPositions = [...safe!.by_category]
                .sort((a, b) => (b.match_score ?? 0) - (a.match_score ?? 0))
                .slice(0, 10);
              const cat = selectedCategory
                ? safe!.by_category.find((c: ResumeByCategory) => c.category === selectedCategory)
                : topPositions[0] ?? null;
              const effectiveCat = cat ?? topPositions[0];
              const matching = effectiveCat?.matching_skills ?? [];
              const toAddRaw = effectiveCat?.skills_to_add ?? [];
              const toAdd = toAddRaw.filter((s) => s.weight >= 5);
              const score = typeof effectiveCat?.match_score === "number" ? effectiveCat.match_score : 0;

              return (
              <>
                <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
                  Compare resume to position
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Select a position. We compare your PDF skills to that position across all companies.
                </Typography>
                <FormControl size="small" sx={{ minWidth: 280, mb: 3 }}>
                  <InputLabel>Position</InputLabel>
                  <Select
                    value={selectedCategory || (topPositions[0]?.category ?? "")}
                    label="Position"
                    onChange={(e: SelectChangeEvent) => setSelectedCategory(e.target.value)}
                  >
                    <MenuItem value="">—</MenuItem>
                    {categories.map((c) => (
                      <MenuItem key={c} value={c}>{c}</MenuItem>
                    ))}
                  </Select>
                </FormControl>

                {effectiveCat && (
                  <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <Box>
                      <Typography variant="overline" color="text.secondary" sx={{ mb: 1.5, display: "block" }}>
                        Top 10 position matches
                      </Typography>
                      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
                        {topPositions.map((p) => (
                          <Chip
                            key={p.category}
                            label={`${p.category} (${p.match_score}/100)`}
                            onClick={() => setSelectedCategory(p.category)}
                            color={p.category === (selectedCategory || topPositions[0]?.category) ? "primary" : "default"}
                            variant={p.category === (selectedCategory || topPositions[0]?.category) ? "filled" : "outlined"}
                            sx={{ cursor: "pointer" }}
                          />
                        ))}
                      </Box>
                    </Box>

                    <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
                      <Typography variant="overline" color="text.secondary">Match score</Typography>
                      <Chip
                        label={`${score}/100`}
                        color={score >= 70 ? "success" : score >= 40 ? "warning" : "default"}
                        sx={{ fontSize: "1rem", fontWeight: 700, py: 1.5, px: 2 }}
                      />
                    </Box>

                    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 4 }}>
                      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                        <Typography variant="overline" color="text.secondary" sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 1.5, justifyContent: "center" }}>
                          <CheckCircleOutlineIcon fontSize="small" /> Matched skills (in your PDF)
                        </Typography>
                        <MatchedSkillsChart data={matching} />
                      </Box>

                      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                        <Typography variant="overline" color="text.secondary" sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 1.5, justifyContent: "center" }}>
                          <AddCircleOutlineIcon fontSize="small" /> Skills to add (≥5 occurrences)
                        </Typography>
                        <SkillsToAddChart data={toAdd} />
                      </Box>
                    </Box>
                  </Box>
                )}
              </>
            );
          })()}
            </Paper>
          </Grow>
          )}
        </Box>
        </Fade>
      )}
    </Box>
  );
}
