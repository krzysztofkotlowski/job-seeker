import type { ComponentProps } from "react";
import { useCallback, useEffect, useRef, useState, memo } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LabelList,
} from "recharts";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import { useTheme, useMediaQuery } from "@mui/material";
import { ChartTooltip } from "../components/ChartTooltip";
import Fade from "@mui/material/Fade";
import Grow from "@mui/material/Grow";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import LinearProgress from "@mui/material/LinearProgress";
import Collapse from "@mui/material/Collapse";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import type { SelectChangeEvent } from "@mui/material/Select";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api/client";
import type {
  EmbeddingStatusResponse,
  Job,
  ResumeAnalyzeResult,
  ResumeByCategory,
  ResumeMatchItem,
  ResumeRecommendation,
  ResumeRecommendationsResponse,
  SkillWithWeight,
} from "../api/types";

const ACCEPT = ".pdf";
/** Resume analyze can be slow with RAG (embed) + large job DB (30k+). */
const ANALYZE_TIMEOUT_MS = 120000;
const SUMMARIZE_TIMEOUT_MS = 120000;
const EMBEDDING_STATUS_POLL_MS = 5000;
const SKILLS_COLLAPSED_MAX_HEIGHT = 64;
const SKILLS_OVERFLOW_FALLBACK_COUNT = 12;

const ECHO_PREFIXES = [
  "Format:",
  "Resume skills:",
  "By role/field",
  "Do not repeat",
  "TASK:",
  "Section 1:",
  "Section 2:",
  "Section 3:",
  "Categories:",
  "Jobs to recommend:",
  "Write the analysis",
  "Analyze the data",
  "Use ONLY",
];

const CATEGORY_MATCH = /^(.+?):\s*match\s*(\d+)\/100\.?\s*(.+)$/m;

/** Convert plain text to basic markdown when model ignores formatting. */
function formatSummaryForMarkdown(text: string): string {
  if (!text?.trim()) return text;

  const lines = text.trim().split("\n");
  const filtered = lines.filter((line) => {
    const t = line.trim();
    return t && !ECHO_PREFIXES.some((p) => t.startsWith(p));
  });
  const cleaned = filtered.join("\n").trim();
  if (!cleaned) return text.trim();

  const categoryBullets: string[] = [];
  const otherLines: string[] = [];
  for (const line of cleaned.split("\n")) {
    const t = line.trim();
    if (!t) {
      otherLines.push("");
      continue;
    }
    const m = t.match(CATEGORY_MATCH);
    if (m) {
      categoryBullets.push(
        `- **${m[1].trim()} (${m[2]}/100)**: ${m[3].trim()}`,
      );
    } else {
      if (t === "Recommended jobs" || t.startsWith("Recommended jobs")) {
        otherLines.push("## Recommended jobs");
      } else {
        otherLines.push(line);
      }
    }
  }

  if (categoryBullets.length > 0) {
    let section = "## Your strongest fields\n\n" + categoryBullets.join("\n");
    const rest = otherLines.join("\n").trim();
    if (rest) section += "\n\n" + rest;
    return section;
  }

  if (/##|\*\*|\[.+\]\(.+\)/.test(cleaned)) return cleaned;

  return cleaned
    .split(/\n\n+/)
    .map((block) => {
      const line = block.trim();
      if (!line) return "";
      if (line.length < 60 && line.endsWith(":"))
        return `## ${line.slice(0, -1)}`;
      return line;
    })
    .filter(Boolean)
    .join("\n\n");
}

function toSkillWithWeight(x: unknown): SkillWithWeight {
  if (
    x &&
    typeof x === "object" &&
    "skill" in x &&
    typeof (x as SkillWithWeight).skill === "string"
  ) {
    const sw = x as SkillWithWeight;
    return {
      skill: sw.skill,
      weight: typeof sw.weight === "number" ? sw.weight : 1,
    };
  }
  return { skill: String(x ?? ""), weight: 1 };
}

/** Raw API response shape (may include legacy fields). */
interface RawResumeResponse {
  extracted_skills?: string[];
  extracted_keywords?: string[];
  match_count?: number;
  matches?: Array<{
    job?: Partial<Job>;
    matched_skills?: string[];
    match_count?: number;
    match_ratio?: number;
  }>;
  by_category?: Array<{
    category?: string;
    job_count?: number;
    match_score?: number;
    matching_skills?: unknown[];
    skills_to_add?: unknown[];
    skills_to_add_required?: unknown[];
    skills_to_add_nice?: unknown[];
  }>;
  message?: string;
  summary?: string;
  recommendations?: ResumeRecommendation[];
}

function toResumeMatchItem(
  m: NonNullable<RawResumeResponse["matches"]>[number],
): ResumeMatchItem {
  const job = (m?.job ?? {}) as Job;
  return {
    job: {
      id: job.id ?? "",
      url: job.url ?? "",
      source: job.source ?? "",
      title: job.title ?? "",
      company: job.company ?? "",
      location: job.location ?? [],
      salary: job.salary ?? null,
      skills_required: job.skills_required ?? [],
      skills_nice_to_have: job.skills_nice_to_have ?? [],
      seniority: job.seniority ?? null,
      work_type: job.work_type ?? null,
      employment_types: job.employment_types ?? [],
      description: job.description ?? null,
      category: job.category ?? null,
      is_reposted: job.is_reposted ?? false,
      original_job_id: job.original_job_id ?? null,
      date_published: job.date_published ?? null,
      date_expires: job.date_expires ?? null,
      date_added: job.date_added ?? "",
      status: (job.status as "new") ?? "new",
      applied_date: job.applied_date ?? null,
      notes: job.notes ?? "",
      saved: job.saved ?? false,
      duplicate_count: job.duplicate_count ?? 1,
    },
    matched_skills: Array.isArray(m?.matched_skills) ? m.matched_skills : [],
    match_count: typeof m?.match_count === "number" ? m.match_count : 0,
    match_ratio: typeof m?.match_ratio === "number" ? m.match_ratio : 0,
  };
}

/** Normalize API response so we support both extracted_skills and legacy extracted_keywords. */
function normalizeResult(
  data: ResumeAnalyzeResult | RawResumeResponse | null,
): ResumeAnalyzeResult | null {
  if (!data || typeof data !== "object") return null;
  const raw = data as RawResumeResponse;
  const extracted = Array.isArray(raw.extracted_skills)
    ? raw.extracted_skills
    : Array.isArray(raw.extracted_keywords)
      ? raw.extracted_keywords
      : [];
  const byCategory: ResumeByCategory[] = (
    Array.isArray(raw.by_category) ? raw.by_category : []
  ).map((cat) => {
    const matching = Array.isArray(cat.matching_skills)
      ? cat.matching_skills.map(toSkillWithWeight)
      : [];
    const toAdd = Array.isArray(cat.skills_to_add)
      ? cat.skills_to_add.map(toSkillWithWeight)
      : [
          ...(Array.isArray(cat.skills_to_add_required)
            ? cat.skills_to_add_required
            : []
          ).map((s) => ({ skill: String(s), weight: 1 })),
          ...(Array.isArray(cat.skills_to_add_nice)
            ? cat.skills_to_add_nice
            : []
          ).map((s) => ({ skill: String(s), weight: 1 })),
        ];
    const total =
      matching.reduce((a, x) => a + x.weight, 0) +
      toAdd.reduce((a, x) => a + x.weight, 0);
    const matchScore =
      total > 0
        ? Math.round((matching.reduce((a, x) => a + x.weight, 0) / total) * 100)
        : 0;
    return {
      category: cat.category ?? "",
      job_count: typeof cat.job_count === "number" ? cat.job_count : 0,
      match_score:
        typeof cat.match_score === "number" ? cat.match_score : matchScore,
      matching_skills: matching,
      skills_to_add: toAdd,
    };
  });
  const matches: ResumeMatchItem[] = Array.isArray(raw.matches)
    ? raw.matches.map(toResumeMatchItem)
    : [];
  return {
    extracted_skills: extracted,
    match_count: typeof raw.match_count === "number" ? raw.match_count : 0,
    matches,
    by_category: byCategory,
    message: raw.message,
    summary: typeof raw.summary === "string" ? raw.summary : undefined,
    recommendations: Array.isArray(raw.recommendations)
      ? raw.recommendations
      : undefined,
  };
}

/** Max skills to display per chart to avoid ugly overflow on large datasets. */
const MAX_SKILLS_IN_CHART = 40;

/** Max chart height so all labels display. Exported for tests. */
export const CHART_MAX_HEIGHT = 1200;
const CHART_ROW_HEIGHT = 44;
const CHART_MIN_HEIGHT = 240;
const CHART_ANIMATION_DURATION = 400;

function chartHeight(itemCount: number): number {
  return Math.min(
    Math.max(itemCount * CHART_ROW_HEIGHT, CHART_MIN_HEIGHT),
    CHART_MAX_HEIGHT,
  );
}

const MatchedSkillsChart = memo(function MatchedSkillsChart({
  data,
  yAxisWidth = 200,
}: {
  data: SkillWithWeight[];
  yAxisWidth?: number;
}) {
  if (data.length === 0)
    return (
      <Typography variant="body2" color="text.secondary">
        None
      </Typography>
    );
  return (
    <ResponsiveContainer width="100%" height={chartHeight(data.length)}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ left: 8, right: 50 }}
        barCategoryGap={4}
        barGap={4}
      >
        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 14 }} />
        <YAxis
          type="category"
          dataKey="skill"
          width={yAxisWidth}
          tick={{ fontSize: 14 }}
        />
        <Tooltip
          content={(props) => (
            <ChartTooltip
              {...(props as ComponentProps<typeof ChartTooltip>)}
              formatter={(v) => [`×${v ?? 0}`, "Occurrences"]}
            />
          )}
          contentStyle={{
            background: "transparent",
            border: "none",
            padding: 0,
          }}
        />
        <Bar
          dataKey="weight"
          fill="#22c55e"
          radius={[0, 6, 6, 0]}
          barSize={28}
          animationDuration={CHART_ANIMATION_DURATION}
        >
          <LabelList
            dataKey="weight"
            position="right"
            formatter={(v) => `×${v ?? 0}`}
            style={{ fontSize: 13, fill: "#166534" }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
});

const SkillsToAddChart = memo(function SkillsToAddChart({
  data,
  yAxisWidth = 200,
}: {
  data: SkillWithWeight[];
  yAxisWidth?: number;
}) {
  if (data.length === 0)
    return (
      <Typography variant="body2" color="text.secondary">
        None
      </Typography>
    );
  return (
    <ResponsiveContainer width="100%" height={chartHeight(data.length)}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ left: 8, right: 50 }}
        barCategoryGap={4}
        barGap={4}
      >
        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 14 }} />
        <YAxis
          type="category"
          dataKey="skill"
          width={yAxisWidth}
          tick={{ fontSize: 14 }}
        />
        <Tooltip
          content={(props) => (
            <ChartTooltip
              {...(props as ComponentProps<typeof ChartTooltip>)}
              formatter={(v) => [`×${v ?? 0}`, "Occurrences"]}
            />
          )}
          contentStyle={{
            background: "transparent",
            border: "none",
            padding: 0,
          }}
        />
        <Bar
          dataKey="weight"
          fill="#ef4444"
          radius={[0, 6, 6, 0]}
          barSize={28}
          animationDuration={CHART_ANIMATION_DURATION}
        >
          <LabelList
            dataKey="weight"
            position="right"
            formatter={(v) => `×${v ?? 0}`}
            style={{ fontSize: 13, fill: "#991b1b" }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
});

/** Normalize ES score to 0-100 for display. */
function normalizeScore(score: number, min: number, max: number): number {
  if (max <= min) return 100;
  return Math.round(((score - min) / (max - min)) * 100);
}

function recommendationSourceLabel(rec: ResumeRecommendation): string {
  const sources = rec.explanation?.sources;
  if (sources?.keyword && sources?.semantic) return "Hybrid";
  if (sources?.semantic) return "Semantic";
  return "Keyword";
}

const RecommendationCard = memo(function RecommendationCard({
  rec,
  relevancePercent,
}: {
  rec: ResumeRecommendation;
  relevancePercent: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const j = rec.job;
  const title = j?.title ?? "Job";
  const company = j?.company ?? "";
  const url = (j?.url ?? "").trim();
  const category = j?.category ?? "";
  const explanation = rec.explanation;
  const inlineMatched = explanation?.matched_skills?.slice(0, 3) ?? [];
  const matchedOverflow = Math.max(
    0,
    (explanation?.matched_skills?.length ?? 0) - inlineMatched.length,
  );
  const categoryLabel =
    explanation?.category_overlap?.category &&
    explanation.category_overlap.match_score != null
      ? `${explanation.category_overlap.category} ${explanation.category_overlap.match_score}/100`
      : null;
  const hasDetails = Boolean(
    (explanation?.matched_skills?.length ?? 0) > inlineMatched.length ||
      (explanation?.missing_skills?.length ?? 0) > 0 ||
      explanation?.category_overlap ||
      explanation?.keyword_rank != null ||
      explanation?.semantic_rank != null,
  );

  return (
    <Paper
      variant="outlined"
      data-testid="recommendation-row"
      sx={{
        px: 2,
        py: 1.5,
        transition: "box-shadow 0.2s ease",
        "&:hover": { boxShadow: 1 },
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "flex-start",
          gap: 1.5,
          justifyContent: "space-between",
        }}
      >
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="subtitle2" fontWeight={600}>
            {title}
          </Typography>
          {company && (
            <Typography variant="body2" color="text.secondary">
              {company}
            </Typography>
          )}
          {explanation?.summary ? (
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ mt: 0.75 }}
            >
              {explanation.summary}
            </Typography>
          ) : null}
          <Box
            sx={{
              mt: 1,
              display: "flex",
              flexWrap: "wrap",
              gap: 0.75,
              alignItems: "center",
            }}
          >
            {inlineMatched.map((skill) => (
              <Chip
                key={skill}
                label={skill}
                size="small"
                color="success"
                variant="outlined"
              />
            ))}
            {matchedOverflow > 0 ? (
              <Chip
                label={`+${matchedOverflow} more skills`}
                size="small"
                variant="outlined"
              />
            ) : null}
            <Chip
              label={recommendationSourceLabel(rec)}
              size="small"
              color="secondary"
              variant="outlined"
            />
            {category && (
              <Chip
                label={category}
                size="small"
                variant="outlined"
              />
            )}
            {categoryLabel ? (
              <Chip
                label={`Category fit ${categoryLabel}`}
                size="small"
                color="primary"
                variant="outlined"
              />
            ) : null}
          </Box>
        </Box>
        <Box
          sx={{
            flexShrink: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-end",
            gap: 1,
            minWidth: "fit-content",
          }}
        >
          <Chip
            label={`${relevancePercent}%`}
            size="small"
            color="primary"
            variant="filled"
            sx={{ fontWeight: 600, fontSize: "0.75rem" }}
          />
          {url && url.startsWith("http") && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                color: "var(--mui-palette-primary-main)",
                textDecoration: "none",
                fontSize: "0.8125rem",
                whiteSpace: "nowrap",
              }}
            >
              <OpenInNewIcon sx={{ fontSize: 16 }} />
              Open
            </a>
          )}
          {hasDetails ? (
            <Button
              size="small"
              onClick={() => setExpanded((prev) => !prev)}
              endIcon={
                expanded ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />
              }
              sx={{ minWidth: 0, px: 0.5 }}
            >
              {expanded ? "Hide details" : "Why this matched"}
            </Button>
          ) : null}
        </Box>
      </Box>
      {hasDetails ? (
        <Collapse in={expanded} timeout="auto" unmountOnExit>
          <Box
            data-testid="recommendation-details"
            sx={{
              mt: 1.5,
              pt: 1.5,
              borderTop: "1px solid",
              borderColor: "divider",
              display: "flex",
              flexDirection: "column",
              gap: 1.25,
            }}
          >
            {explanation?.matched_skills?.length ? (
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Matched skills
                </Typography>
                <Box sx={{ mt: 0.5, display: "flex", flexWrap: "wrap", gap: 0.75 }}>
                  {explanation.matched_skills.map((skill) => (
                    <Chip
                      key={skill}
                      label={skill}
                      size="small"
                      color="success"
                      variant="outlined"
                    />
                  ))}
                </Box>
              </Box>
            ) : null}
            {explanation?.missing_skills?.length ? (
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Missing skills to strengthen this match
                </Typography>
                <Box sx={{ mt: 0.5, display: "flex", flexWrap: "wrap", gap: 0.75 }}>
                  {explanation.missing_skills.map((skill) => (
                    <Chip key={skill} label={skill} size="small" variant="outlined" />
                  ))}
                </Box>
              </Box>
            ) : null}
            {categoryLabel ? (
              <Typography variant="caption" color="text.secondary">
                Category overlap: {categoryLabel}
              </Typography>
            ) : null}
            {explanation ? (
              <Typography variant="caption" color="text.secondary">
                Search signals:{" "}
                {[
                  explanation.keyword_rank != null
                    ? `keyword #${explanation.keyword_rank}`
                    : null,
                  explanation.semantic_rank != null
                    ? `semantic #${explanation.semantic_rank}`
                    : null,
                ]
                  .filter(Boolean)
                  .join(" · ") || recommendationSourceLabel(rec)}
              </Typography>
            ) : null}
          </Box>
        </Collapse>
      ) : null}
    </Paper>
  );
});

export function ResumeAnalysisPage() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const chartYAxisWidth = isMobile ? 100 : 200;

  const [result, setResult] = useState<ResumeAnalyzeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [chartsReady, setChartsReady] = useState(false);
  const [embeddingStatus, setEmbeddingStatus] =
    useState<EmbeddingStatusResponse | null>(null);
  const [recommendationsLoading, setRecommendationsLoading] = useState(false);
  const [recommendationsError, setRecommendationsError] = useState<
    string | null
  >(null);
  const [recommendationsNotice, setRecommendationsNotice] = useState<
    { severity: "info" | "warning"; message: string } | null
  >(null);
  const [recommendationsStatus, setRecommendationsStatus] = useState<
    ResumeRecommendationsResponse["status"] | null
  >(null);
  const [recommendationsMessage, setRecommendationsMessage] = useState<
    string | null
  >(null);
  const recommendationsFingerprintRef = useRef<string | null>(null);
  const skillsTrayRef = useRef<HTMLDivElement | null>(null);
  const [skillsExpanded, setSkillsExpanded] = useState(false);
  const [skillsOverflow, setSkillsOverflow] = useState(false);
  const safe = normalizeResult(result);
  const extractedSkills = safe?.extracted_skills;
  const existingRecommendations = safe?.recommendations;
  const hasExtractedSkills = Boolean(safe?.extracted_skills?.length);
  const currentOrActiveRun = embeddingStatus?.run ?? embeddingStatus?.active_run;
  const currentRunStatus = currentOrActiveRun?.status ?? null;
  const isEmbeddingRunActive =
    currentRunStatus === "queued" || currentRunStatus === "running";
  const activeIndexedDocuments = embeddingStatus?.active_indexed_documents ?? 0;
  const recommendationsTerminal =
    recommendationsStatus !== null &&
    ["ok", "fallback", "reindex_required", "active_embedding_unavailable", "unavailable"].includes(
      recommendationsStatus,
    );
  const shouldPollEmbeddingStatus = Boolean(
    safe &&
      embeddingStatus?.available &&
      (isEmbeddingRunActive ||
        (activeIndexedDocuments === 0 && !recommendationsTerminal)),
  );
  const recommendationsReady = Boolean(
    hasExtractedSkills && embeddingStatus?.available && activeIndexedDocuments > 0,
  );
  const recommendationFingerprint = hasExtractedSkills
    ? JSON.stringify({
        skills: [...(safe?.extracted_skills ?? [])].sort(),
        run_id: currentOrActiveRun?.id ?? null,
        run_status: currentRunStatus,
        active_docs: activeIndexedDocuments,
      })
    : null;
  const recommendationCaption = !hasExtractedSkills
    ? null
    : isEmbeddingRunActive
      ? `Indexing is still running: ${(currentOrActiveRun?.processed ?? 0).toLocaleString()} / ${(currentOrActiveRun?.target_total ?? 0).toLocaleString()}. Recommendations will retry automatically.`
      : recommendationsStatus === "reindex_required" ||
          recommendationsStatus === "active_embedding_unavailable" ||
          recommendationsStatus === "unavailable"
        ? recommendationsMessage ||
          "Recommendations need a rebuilt or available active vector index."
        : embeddingStatus?.available && activeIndexedDocuments === 0
          ? "No active vector index yet. Run Re-index all."
          : recommendationsStatus === "ok" ||
              recommendationsStatus === "fallback"
            ? "No matching jobs found. Try adjusting your skills or index more jobs."
            : embeddingStatus?.available
              ? "Recommendations will load automatically when the active vector index is ready."
              : "Enable RAG and sync embeddings for job recommendations.";

  useEffect(() => {
    api
      .listCategories()
      .then(setCategories)
      .catch(() => {});
  }, []);

  const fetchEmbeddingStatus = useCallback(async () => {
    try {
      const s = await api.embeddingStatus();
      setEmbeddingStatus(s);
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
    if (!shouldPollEmbeddingStatus) return;
    const id = setInterval(fetchEmbeddingStatus, EMBEDDING_STATUS_POLL_MS);
    return () => clearInterval(id);
  }, [fetchEmbeddingStatus, shouldPollEmbeddingStatus]);

  useEffect(() => {
    if (!safe) return;
    const handleFocus = () => {
      fetchEmbeddingStatus();
    };
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [fetchEmbeddingStatus, safe]);

  useEffect(() => {
    if (safe?.summary) fetchEmbeddingStatus();
  }, [safe?.summary, fetchEmbeddingStatus]);

  useEffect(() => {
    if (!safe?.extracted_skills?.length) {
      setSkillsOverflow(false);
      return;
    }
    const measure = () => {
      const tray = skillsTrayRef.current;
      if (!tray) return;
      const measuredOverflow =
        tray.scrollHeight > SKILLS_COLLAPSED_MAX_HEIGHT + 1;
      setSkillsOverflow(
        measuredOverflow ||
          safe.extracted_skills.length > SKILLS_OVERFLOW_FALLBACK_COUNT,
      );
    };
    const frame = requestAnimationFrame(measure);
    window.addEventListener("resize", measure);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", measure);
    };
  }, [safe?.extracted_skills]);

  useEffect(() => {
    if (
      !recommendationsReady ||
      (existingRecommendations?.length ?? 0) > 0 ||
      !recommendationFingerprint ||
      recommendationsFingerprintRef.current === recommendationFingerprint
    ) {
      return;
    }
    let cancelled = false;
    recommendationsFingerprintRef.current = recommendationFingerprint;
    setRecommendationsLoading(true);
    setRecommendationsError(null);
    api
      .resumeRecommendations(extractedSkills ?? [])
      .then((res: ResumeRecommendationsResponse) => {
        if (!cancelled) {
          setRecommendationsStatus(res.status);
          setRecommendationsMessage(res.message ?? null);
          setResult((prev) =>
            prev
              ? { ...prev, recommendations: res.recommendations ?? [] }
              : prev,
          );
          if (
            res.status === "reindex_required" ||
            res.status === "active_embedding_unavailable" ||
            res.status === "unavailable"
          ) {
            setRecommendationsNotice({
              severity:
                res.status === "reindex_required" ? "warning" : "info",
              message:
                res.message ||
                "Recommendations need a rebuilt or available active vector index.",
            });
          } else if (res.status === "fallback") {
            setRecommendationsNotice({
              severity: "info",
              message:
                res.message ||
                "Recommendations are using keyword fallback on the active Elasticsearch index.",
            });
          } else if (
            res.active_run &&
            res.config_matches_active === false &&
            !res.message
          ) {
            setRecommendationsNotice({
              severity: "info",
              message: `Recommendations are using the older active index built with ${res.active_run.embed_model} (${res.active_run.embed_dims} dims) until you rebuild.`,
            });
          } else {
            setRecommendationsNotice(null);
          }
        }
      })
      .catch((e) => {
        if (!cancelled) {
          recommendationsFingerprintRef.current = null;
          setRecommendationsStatus(null);
          setRecommendationsMessage(null);
          setRecommendationsNotice(null);
          setRecommendationsError(
            e instanceof Error ? e.message : "Failed to load recommendations",
          );
        }
      })
      .finally(() => {
        setRecommendationsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    recommendationFingerprint,
    recommendationsReady,
    existingRecommendations,
    extractedSkills,
  ]);

  useEffect(() => {
    if (!safe) {
      setChartsReady(false);
      return;
    }
    const id = requestAnimationFrame(() => setChartsReady(true));
    return () => cancelAnimationFrame(id);
  }, [safe]);

  const handleFile = useCallback(async (file: File | null) => {
    if (!file) return;
    setError(null);
    setResult(null);
    setSummaryError(null);
    setRecommendationsError(null);
    setRecommendationsNotice(null);
    setRecommendationsStatus(null);
    setRecommendationsMessage(null);
    setSkillsExpanded(false);
    setSkillsOverflow(false);
    recommendationsFingerprintRef.current = null;
    setLoading(true);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), ANALYZE_TIMEOUT_MS);
    try {
      const data = await api.resumeAnalyze(file, controller.signal);
      const normalized = normalizeResult(data) ?? data;
      setResult(normalized);
      const top = (normalized?.by_category ?? []).sort(
        (a, b) => (b.match_score ?? 0) - (a.match_score ?? 0),
      )[0];
      setSelectedCategory(top?.category ?? "");
    } catch (e) {
      if (e instanceof Error) {
        setError(
          e.name === "AbortError" ? "Request timed out. Try again." : e.message,
        );
      } else {
        setError("Upload failed");
      }
    } finally {
      clearTimeout(timeoutId);
      setLoading(false);
    }
  }, []);

  const handleSummarize = useCallback(async () => {
    if (!safe) return;
    setSummaryError(null);
    setSummaryLoading(true);
    setResult((prev) => (prev ? { ...prev, summary: "" } : prev));
    const controller = new AbortController();
    const timeoutId = setTimeout(
      () => controller.abort(),
      SUMMARIZE_TIMEOUT_MS,
    );
    try {
      // Send data with job URLs for markdown links; dedupe by (title, company)
      const seen = new Set<string>();
      const topMatches: {
        job: { title?: string; company?: string; url?: string };
        matched_skills: string[];
        match_count: number;
      }[] = [];
      for (const m of safe.matches) {
        const key = `${m.job?.title ?? ""}|${m.job?.company ?? ""}`;
        if (!seen.has(key) && key !== "|") {
          seen.add(key);
          topMatches.push({
            job: {
              title: m.job?.title,
              company: m.job?.company,
              url: m.job?.url,
            },
            matched_skills: m.matched_skills,
            match_count: m.match_count,
          });
          if (topMatches.length >= 5) break;
        }
      }
      const topCategories = [...safe.by_category]
        .sort((a, b) => (b.match_score ?? 0) - (a.match_score ?? 0))
        .slice(0, 5)
        .map((c) => ({
          category: c.category,
          match_score: c.match_score,
          matching_skills: c.matching_skills?.slice(0, 8) ?? [],
          skills_to_add: c.skills_to_add?.slice(0, 5) ?? [],
        }));
      const { summary: fullSummary } = await api.resumeSummarizeStream(
        {
          extracted_skills: safe.extracted_skills,
          matches: topMatches,
          by_category: topCategories,
        },
        (chunk) => {
          setResult((prev) =>
            prev ? { ...prev, summary: (prev.summary ?? "") + chunk } : prev,
          );
        },
        controller.signal,
      );
      const trimmed = fullSummary.trim();
      setResult((prev) => (prev ? { ...prev, summary: trimmed } : prev));
      if (!trimmed) {
        setSummaryError(
          "AI summary unavailable. Check Settings > AI Config: ensure your provider is configured (Ollama running or OpenAI API key valid).",
        );
      }
    } catch (e) {
      if (e instanceof Error) {
        setSummaryError(
          e.name === "AbortError" ? "Summary timed out. Try again." : e.message,
        );
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
          Upload your resume as a PDF. We extract keywords and skills from the
          text and compare them with our job offers to show the best matches.
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
          <Typography
            variant="caption"
            display="block"
            sx={{ mt: 1 }}
            color="text.secondary"
          >
            or drag and drop a PDF here
          </Typography>
        </Box>

        {loading && (
          <LinearProgress sx={{ mt: 2, transition: "opacity 0.2s ease" }} />
        )}
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
                data-testid="skills-card"
                sx={{
                  p: 2.5,
                  border: "1px solid",
                  borderColor: "divider",
                  transition: "box-shadow 0.3s ease",
                  "&:hover": { boxShadow: 1 },
                }}
              >
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "flex-start",
                    justifyContent: "space-between",
                    gap: 2,
                    mb: 1.5,
                  }}
                >
                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="subtitle1" fontWeight={600}>
                      Skills from your PDF (in our system) (
                      {safe.extracted_skills.length})
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Skills we matched directly against the jobs database.
                    </Typography>
                  </Box>
                  <Chip
                    label={`${safe.extracted_skills.length} skills`}
                    size="small"
                    color="primary"
                    variant="outlined"
                  />
                </Box>
                <Box
                  ref={skillsTrayRef}
                  data-testid="skills-tray"
                  sx={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 0.75,
                    overflow: "hidden",
                    maxHeight: skillsExpanded
                      ? "none"
                      : `${SKILLS_COLLAPSED_MAX_HEIGHT}px`,
                    transition: "max-height 0.2s ease",
                  }}
                >
                  {safe.extracted_skills.map((k) => (
                    <Chip
                      key={k}
                      label={k}
                      size="small"
                      variant="outlined"
                      color="primary"
                    />
                  ))}
                </Box>
                {skillsOverflow ? (
                  <Button
                    size="small"
                    onClick={() => setSkillsExpanded((prev) => !prev)}
                    aria-expanded={skillsExpanded}
                    sx={{
                      mt: 1.5,
                      px: 0,
                      minWidth: 0,
                      textTransform: "none",
                      fontWeight: 600,
                      alignSelf: "flex-start",
                    }}
                  >
                    {skillsExpanded ? "Show fewer" : "Show all skills"}
                  </Button>
                ) : null}

                {safe.message && (
                  <Alert severity="info" sx={{ mt: 2 }}>
                    {safe.message}
                  </Alert>
                )}
              </Paper>
            </Grow>

            <Grow in timeout={450}>
              <Paper
                data-testid="ai-card"
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
                <Typography
                  variant="subtitle1"
                  fontWeight={600}
                  sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}
                >
                  <AutoAwesomeIcon color="primary" fontSize="small" />
                  AI Summary & Recommendations
                </Typography>
                {recommendationsNotice ? (
                  <Alert severity={recommendationsNotice.severity} sx={{ mt: 3 }}>
                    {recommendationsNotice.message}
                  </Alert>
                ) : null}
                {safe.recommendations && safe.recommendations.length > 0 ? (
                  <Box sx={{ mt: 3 }}>
                    <Typography
                      variant="subtitle2"
                      fontWeight={600}
                      sx={{ mb: 1.5 }}
                    >
                      Recommended jobs (hybrid search)
                    </Typography>
                    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                      {(() => {
                        const recs = safe.recommendations;
                        const scores = recs
                          .map((r) => r.score ?? 0)
                          .filter((s) => s > 0);
                        const min = scores.length ? Math.min(...scores) : 0;
                        const max = scores.length ? Math.max(...scores) : 0;
                        return recs.map((rec, i) => (
                          <RecommendationCard
                            key={rec.job?.id ?? i}
                            rec={rec}
                            relevancePercent={
                              rec.score != null && max > min
                                ? normalizeScore(rec.score, min, max)
                                : Math.max(50, 100 - i * 10)
                            }
                          />
                        ));
                      })()}
                    </Box>
                  </Box>
                ) : recommendationsError ? (
                  <Alert
                    severity="error"
                    sx={{ mt: 3 }}
                    onClose={() => setRecommendationsError(null)}
                  >
                    {recommendationsError}
                  </Alert>
                ) : recommendationsLoading ? (
                  <Box sx={{ mt: 3 }}>
                    <Typography
                      variant="subtitle2"
                      fontWeight={600}
                      sx={{ mb: 1 }}
                    >
                      Recommended jobs (hybrid search)
                    </Typography>
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ mb: 1 }}
                    >
                      Loading recommendations...
                    </Typography>
                    <LinearProgress sx={{ borderRadius: 1 }} />
                  </Box>
                ) : hasExtractedSkills &&
                  recommendationCaption &&
                  recommendationCaption !== recommendationsNotice?.message ? (
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: "block", mt: 2 }}
                  >
                    {recommendationCaption}
                  </Typography>
                ) : null}
                <Box sx={{ mt: 3 }}>
                  {!safe.summary && (
                    <Box>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{ mb: 2 }}
                      >
                        Get personalized career advice based on your resume and
                        job market matches.
                      </Typography>
                      <Button
                        variant="contained"
                        startIcon={<AutoAwesomeIcon />}
                        onClick={handleSummarize}
                        disabled={
                          summaryLoading || safe.extracted_skills.length === 0
                        }
                        sx={{ textTransform: "none", fontWeight: 600 }}
                      >
                        {summaryLoading ? "Generating..." : "Generate AI summary"}
                      </Button>
                    </Box>
                  )}
                  {summaryLoading && (
                    <LinearProgress sx={{ mt: 2, borderRadius: 1 }} />
                  )}
                  {summaryError && (
                    <Alert
                      severity="error"
                      sx={{ mt: 2 }}
                      onClose={() => setSummaryError(null)}
                    >
                      {summaryError}
                    </Alert>
                  )}
                </Box>
                {safe.summary ? (
                  <Box sx={{ mt: 3 }}>
                    <Typography
                      variant="subtitle2"
                      fontWeight={600}
                      sx={{ mb: 1.5 }}
                    >
                      AI summary
                    </Typography>
                    <Box
                      sx={{
                        "& h1": {
                          fontSize: "1.25rem",
                          fontWeight: 600,
                          mt: 2,
                          mb: 1,
                        },
                        "& h2": {
                          fontSize: "1.1rem",
                          fontWeight: 600,
                          mt: 2,
                          mb: 1,
                        },
                        "& h3": {
                          fontSize: "1rem",
                          fontWeight: 600,
                          mt: 1.5,
                          mb: 0.5,
                        },
                        "& p": { mb: 1 },
                        "& ul": { pl: 2, mb: 1 },
                        "& ol": { pl: 2, mb: 1 },
                        "& li": { mb: 0.25 },
                        "& strong": { fontWeight: 600 },
                        "& a": {
                          color: "primary.main",
                          textDecoration: "underline",
                        },
                        "& code": {
                          fontFamily: "monospace",
                          bgcolor: "action.hover",
                          px: 0.5,
                          borderRadius: 0.5,
                        },
                        "& pre": {
                          overflow: "auto",
                          p: 1.5,
                          borderRadius: 1,
                          bgcolor: "action.hover",
                        },
                        lineHeight: 1.7,
                      }}
                    >
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          a: ({ href, children }) => (
                            <a
                              href={href}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              {children}
                            </a>
                          ),
                        }}
                      >
                        {formatSummaryForMarkdown(safe.summary)}
                      </ReactMarkdown>
                    </Box>
                  </Box>
                ) : null}
              </Paper>
            </Grow>

            {categories.length > 0 &&
              safe.by_category.length > 0 &&
              chartsReady && (
                <Grow in timeout={550}>
                  <Paper sx={{ p: 3, transition: "box-shadow 0.3s ease" }}>
                    {(() => {
                      const topPositions = [...safe!.by_category]
                        .sort(
                          (a, b) => (b.match_score ?? 0) - (a.match_score ?? 0),
                        )
                        .slice(0, 10);
                      const cat = selectedCategory
                        ? safe!.by_category.find(
                            (c: ResumeByCategory) =>
                              c.category === selectedCategory,
                          )
                        : (topPositions[0] ?? null);
                      const effectiveCat = cat ?? topPositions[0];
                      const matchingRaw = effectiveCat?.matching_skills ?? [];
                      const matching = [...matchingRaw]
                        .sort((a, b) => (b.weight ?? 0) - (a.weight ?? 0))
                        .slice(0, MAX_SKILLS_IN_CHART);
                      const toAddRaw = effectiveCat?.skills_to_add ?? [];
                      const toAddFiltered = toAddRaw.filter(
                        (s) => s.weight >= 5,
                      );
                      const toAdd = [...toAddFiltered]
                        .sort((a, b) => (b.weight ?? 0) - (a.weight ?? 0))
                        .slice(0, MAX_SKILLS_IN_CHART);
                      const score =
                        typeof effectiveCat?.match_score === "number"
                          ? effectiveCat.match_score
                          : 0;

                      return (
                        <>
                          <Typography
                            variant="subtitle1"
                            fontWeight={600}
                            sx={{ mb: 2 }}
                          >
                            Compare resume to position
                          </Typography>
                          <Typography
                            variant="body2"
                            color="text.secondary"
                            sx={{ mb: 2 }}
                          >
                            Select a position. We compare your PDF skills to
                            that position across all companies.
                          </Typography>
                          <FormControl
                            size="small"
                            sx={{ minWidth: { xs: "100%", sm: 280 }, mb: 3 }}
                          >
                            <InputLabel>Position</InputLabel>
                            <Select
                              value={
                                selectedCategory ||
                                (topPositions[0]?.category ?? "")
                              }
                              label="Position"
                              onChange={(e: SelectChangeEvent) =>
                                setSelectedCategory(e.target.value)
                              }
                            >
                              <MenuItem value="">—</MenuItem>
                              {categories.map((c) => (
                                <MenuItem key={c} value={c}>
                                  {c}
                                </MenuItem>
                              ))}
                            </Select>
                          </FormControl>

                          {effectiveCat && (
                            <Box
                              sx={{
                                display: "flex",
                                flexDirection: "column",
                                gap: 4,
                              }}
                            >
                              <Box>
                                <Typography
                                  variant="overline"
                                  color="text.secondary"
                                  sx={{ mb: 1.5, display: "block" }}
                                >
                                  Top 10 position matches
                                </Typography>
                                <Box
                                  sx={{
                                    display: "flex",
                                    flexWrap: "wrap",
                                    gap: 1,
                                  }}
                                >
                                  {topPositions.map((p) => (
                                    <Chip
                                      key={p.category}
                                      label={`${p.category} (${p.match_score}/100)`}
                                      onClick={() =>
                                        setSelectedCategory(p.category)
                                      }
                                      color={
                                        p.category ===
                                        (selectedCategory ||
                                          topPositions[0]?.category)
                                          ? "primary"
                                          : "default"
                                      }
                                      variant={
                                        p.category ===
                                        (selectedCategory ||
                                          topPositions[0]?.category)
                                          ? "filled"
                                          : "outlined"
                                      }
                                      sx={{ cursor: "pointer" }}
                                    />
                                  ))}
                                </Box>
                              </Box>

                              <Box
                                sx={{
                                  display: "flex",
                                  alignItems: "center",
                                  gap: 2,
                                  flexWrap: "wrap",
                                }}
                              >
                                <Typography
                                  variant="overline"
                                  color="text.secondary"
                                >
                                  Match score
                                </Typography>
                                <Chip
                                  label={`${score}/100`}
                                  color={
                                    score >= 70
                                      ? "success"
                                      : score >= 40
                                        ? "warning"
                                        : "default"
                                  }
                                  sx={{
                                    fontSize: "1rem",
                                    fontWeight: 700,
                                    py: 1.5,
                                    px: 2,
                                  }}
                                />
                              </Box>

                              <Box
                                sx={{
                                  display: "grid",
                                  gridTemplateColumns: {
                                    xs: "1fr",
                                    md: "1fr 1fr",
                                  },
                                  gap: 4,
                                }}
                              >
                                <Box
                                  sx={{
                                    display: "flex",
                                    flexDirection: "column",
                                    alignItems: "center",
                                  }}
                                >
                                  <Typography
                                    variant="overline"
                                    color="text.secondary"
                                    sx={{
                                      display: "flex",
                                      alignItems: "center",
                                      gap: 0.5,
                                      mb: 1.5,
                                      justifyContent: "center",
                                    }}
                                  >
                                    <CheckCircleOutlineIcon fontSize="small" />{" "}
                                    Matched skills (in your PDF)
                                    {matchingRaw.length > MAX_SKILLS_IN_CHART &&
                                      ` — top ${MAX_SKILLS_IN_CHART}`}
                                  </Typography>
                                  <MatchedSkillsChart data={matching} yAxisWidth={chartYAxisWidth} />
                                </Box>

                                <Box
                                  sx={{
                                    display: "flex",
                                    flexDirection: "column",
                                    alignItems: "center",
                                  }}
                                >
                                  <Typography
                                    variant="overline"
                                    color="text.secondary"
                                    sx={{
                                      display: "flex",
                                      alignItems: "center",
                                      gap: 0.5,
                                      mb: 1.5,
                                      justifyContent: "center",
                                    }}
                                  >
                                    <AddCircleOutlineIcon fontSize="small" />{" "}
                                    Skills to add (≥5 occurrences)
                                    {toAddRaw.filter((s) => s.weight >= 5)
                                      .length > MAX_SKILLS_IN_CHART &&
                                      ` — top ${MAX_SKILLS_IN_CHART}`}
                                  </Typography>
                                  <SkillsToAddChart data={toAdd} yAxisWidth={chartYAxisWidth} />
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
