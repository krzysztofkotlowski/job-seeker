import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import InputAdornment from "@mui/material/InputAdornment";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import type { SelectChangeEvent } from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import Chip from "@mui/material/Chip";
import Pagination from "@mui/material/Pagination";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Autocomplete from "@mui/material/Autocomplete";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import SearchIcon from "@mui/icons-material/Search";
import FilterListIcon from "@mui/icons-material/FilterList";
import InboxIcon from "@mui/icons-material/Inbox";
import { api } from "../api/client";
import type { Job, PaginatedResponse } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";

const STATUS_OPTIONS = [
  { value: "", label: "All Statuses" },
  { value: "new", label: "New" },
  { value: "applied", label: "Applied" },
  { value: "interview", label: "Interview" },
  { value: "offer", label: "Offer" },
  { value: "rejected", label: "Rejected" },
];

const SOURCE_OPTIONS = [
  { value: "", label: "All Sources" },
  { value: "justjoin.it", label: "JustJoin.it" },
  { value: "nofluffjobs.com", label: "NoFluffJobs" },
];

const REPOSTED_OPTIONS = [
  { value: "", label: "All Posts" },
  { value: "true", label: "Reposted Only" },
  { value: "false", label: "Original Only" },
];

const SORT_OPTIONS = [
  { value: "", label: "Newest First" },
  { value: "salary_desc", label: "Salary High → Low" },
  { value: "salary_asc", label: "Salary Low → High" },
];

const PER_PAGE = 50;

export function JobListPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<PaginatedResponse<Job> | null>(null);
  const [loading, setLoading] = useState(true);
  const [workTypes, setWorkTypes] = useState<string[]>([]);
  const [locations, setLocations] = useState<string[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [seniorities, setSeniorities] = useState<string[]>([]);
  const [topSkills, setTopSkills] = useState<string[]>([]);
  const [showFilters, setShowFilters] = useState(true);

  const page = Number(searchParams.get("page") || "1");
  const status = searchParams.get("status") || "";
  const source = searchParams.get("source") || "";
  const search = searchParams.get("search") || "";
  const reposted = searchParams.get("is_reposted") || "";
  const sortBy = searchParams.get("sort_by") || "";
  const workType = searchParams.get("work_type") || "";
  const location = searchParams.get("location") || "";
  const category = searchParams.get("category") || "";
  const seniority = searchParams.get("seniority") || "";
  const skill = searchParams.get("skill") || "";

  useEffect(() => {
    Promise.all([
      api.listWorkTypes().then(setWorkTypes),
      api.listLocations().then(setLocations),
      api.listCategories().then(setCategories),
      api.listSeniorities().then(setSeniorities),
      api.listTopSkills(100).then(setTopSkills),
    ]).catch(() => {});
  }, []);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.listJobs({
        page,
        per_page: PER_PAGE,
        status: status || undefined,
        source: source || undefined,
        search: search || undefined,
        is_reposted: reposted === "true" ? true : reposted === "false" ? false : undefined,
        sort_by: sortBy || undefined,
        work_type: workType || undefined,
        location: location || undefined,
        category: category || undefined,
        seniority: seniority || undefined,
        skill: skill || undefined,
      });
      setData(result);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [page, status, source, search, reposted, sortBy, workType, location, category, seniority, skill]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    next.set("page", "1");
    setSearchParams(next);
  };

  const clearFilters = () => {
    setSearchParams({ page: "1" });
  };

  const activeFilters: { key: string; label: string }[] = [];
  if (status) activeFilters.push({ key: "status", label: `Status: ${status}` });
  if (source) activeFilters.push({ key: "source", label: `Source: ${source}` });
  if (category) activeFilters.push({ key: "category", label: `Category: ${category}` });
  if (seniority) activeFilters.push({ key: "seniority", label: `Seniority: ${seniority}` });
  if (workType) activeFilters.push({ key: "work_type", label: `Work: ${workType}` });
  if (location) activeFilters.push({ key: "location", label: `Location: ${location}` });
  if (skill) activeFilters.push({ key: "skill", label: `Skill: ${skill}` });
  if (reposted) activeFilters.push({ key: "is_reposted", label: reposted === "true" ? "Reposted" : "Original" });
  if (sortBy) activeFilters.push({ key: "sort_by", label: `Sort: ${SORT_OPTIONS.find((o) => o.value === sortBy)?.label ?? sortBy}` });

  const jobs = data?.items ?? [];

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {/* Header */}
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Typography variant="body2" color="text.secondary">
          {data ? (
            <>
              <strong>{data.total.toLocaleString()}</strong> job{data.total !== 1 ? "s" : ""} found
            </>
          ) : (
            "Loading..."
          )}
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          {activeFilters.length > 0 && (
            <Button size="small" color="error" onClick={clearFilters}>
              Clear all
            </Button>
          )}
          <Button
            size="small"
            variant="outlined"
            startIcon={<FilterListIcon />}
            onClick={() => setShowFilters((v) => !v)}
          >
            Filters
            {activeFilters.length > 0 && (
              <Chip label={activeFilters.length} size="small" color="primary" sx={{ ml: 1, height: 20, fontSize: 11 }} />
            )}
          </Button>
        </Box>
      </Box>

      <Paper elevation={0} sx={{ border: 1, borderColor: "divider", borderRadius: 2, overflow: "hidden" }}>
        {/* Search */}
        <Box sx={{ p: 2, borderBottom: 1, borderColor: "divider" }}>
          <TextField
            fullWidth
            size="small"
            defaultValue={search}
            onKeyDown={(e) => {
              if (e.key === "Enter") setFilter("search", (e.target as HTMLInputElement).value);
            }}
            onBlur={(e) => setFilter("search", e.target.value)}
            placeholder="Search by title, company, skills..."
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" color="action" />
                  </InputAdornment>
                ),
              },
            }}
          />
        </Box>

        {/* Filters */}
        <Collapse in={showFilters}>
          <Box sx={{ px: 2, py: 1.5, borderBottom: 1, borderColor: "divider", bgcolor: "grey.50" }}>
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", md: "1fr 1fr 1fr 1fr", lg: "repeat(5, 1fr)" }, gap: 1.5 }}>
              <FilterSelect label="Status" value={status} onChange={(v) => setFilter("status", v)} options={STATUS_OPTIONS} />
              <FilterSelect label="Source" value={source} onChange={(v) => setFilter("source", v)} options={SOURCE_OPTIONS} />
              <FilterSelect label="Category" value={category} onChange={(v) => setFilter("category", v)} options={[{ value: "", label: "All Categories" }, ...categories.map((c) => ({ value: c, label: c }))]} />
              <FilterSelect label="Seniority" value={seniority} onChange={(v) => setFilter("seniority", v)} options={[{ value: "", label: "All Seniorities" }, ...seniorities.map((s) => ({ value: s, label: s }))]} />
              <FilterSelect label="Work Type" value={workType} onChange={(v) => setFilter("work_type", v)} options={[{ value: "", label: "All Work Types" }, ...workTypes.map((wt) => ({ value: wt, label: wt }))]} />
            </Box>
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", md: "1fr 1fr 1fr 1fr" }, gap: 1.5, mt: 1.5 }}>
              <FilterSelect label="Location" value={location} onChange={(v) => setFilter("location", v)} options={[{ value: "", label: "All Locations" }, ...locations.map((loc) => ({ value: loc, label: loc }))]} />
              <FilterSelect label="Reposted" value={reposted} onChange={(v) => setFilter("is_reposted", v)} options={REPOSTED_OPTIONS} />
              <FilterSelect label="Sort By" value={sortBy} onChange={(v) => setFilter("sort_by", v)} options={SORT_OPTIONS} />
              <Autocomplete
                size="small"
                freeSolo
                options={topSkills}
                value={skill || null}
                onChange={(_e, val) => setFilter("skill", val ?? "")}
                renderInput={(params) => <TextField {...params} label="Skill" />}
              />
            </Box>

            {activeFilters.length > 0 && (
              <>
                <Divider sx={{ my: 1.5 }} />
                <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                  {activeFilters.map((f) => (
                    <Chip
                      key={f.key}
                      label={f.label}
                      size="small"
                      color="primary"
                      variant="outlined"
                      onDelete={() => setFilter(f.key, "")}
                    />
                  ))}
                </Box>
              </>
            )}
          </Box>
        </Collapse>

        {/* Content */}
        {loading ? (
          <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 8 }}>
            <CircularProgress size={32} />
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
              Loading jobs...
            </Typography>
          </Box>
        ) : jobs.length === 0 ? (
          <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 8, color: "text.secondary" }}>
            <InboxIcon sx={{ fontSize: 48, mb: 1, color: "grey.400" }} />
            <Typography variant="h6" color="text.secondary">No jobs found</Typography>
            <Typography variant="body2">Try changing filters or importing jobs first</Typography>
          </Box>
        ) : (
          <Box>
            {jobs.map((job, idx) => {
              const sal = formatSalary(job);
              return (
                <Box key={job.id}>
                  {idx > 0 && <Divider />}
                  <Box
                    onClick={() => navigate(`/jobs/${job.id}`)}
                    sx={{
                      p: 2,
                      cursor: "pointer",
                      "&:hover": { bgcolor: "grey.50" },
                      transition: "background 0.15s",
                    }}
                  >
                    <Box sx={{ display: "flex", justifyContent: "space-between", gap: 2 }}>
                      <Box sx={{ minWidth: 0, flex: 1 }}>
                        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
                          <Typography
                            variant="h6"
                            sx={{
                              fontWeight: 700,
                              fontSize: "1.1rem",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {job.title}
                          </Typography>
                          <StatusBadge status={job.status} />
                          {job.is_reposted && (
                            <Chip label="Reposted" size="small" color="warning" variant="outlined" sx={{ height: 20, fontSize: 11 }} />
                          )}
                        </Box>
                        <Typography variant="subtitle1" fontWeight={600} color="text.primary">
                          {job.company}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {job.location.join(", ") || "No location"}
                          {job.work_type ? ` · ${job.work_type}` : ""}
                          {job.category ? ` · ${job.category}` : ""}
                          {job.seniority ? ` · ${job.seniority}` : ""}
                        </Typography>
                        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 1 }}>
                          {job.skills_required.slice(0, 6).map((s) => (
                            <Chip key={s} label={s} size="small" variant="outlined" color="primary" sx={{ height: 22, fontSize: 11 }} />
                          ))}
                          {job.skills_required.length > 6 && (
                            <Typography variant="caption" color="text.secondary">
                              +{job.skills_required.length - 6} more
                            </Typography>
                          )}
                        </Box>
                      </Box>
                      <Box sx={{ textAlign: "right", flexShrink: 0 }}>
                        <Typography variant="body2" fontWeight={700} color="success.dark">{sal.plnLine}</Typography>
                        {sal.hourlyLine && (
                          <Typography variant="caption" color="text.secondary">{sal.hourlyLine}</Typography>
                        )}
                        {sal.originalLine && (
                          <Typography variant="caption" display="block" color="text.disabled" sx={{ mt: 0.25 }}>{sal.originalLine}</Typography>
                        )}
                        <Typography variant="caption" display="block" color="text.disabled" sx={{ mt: 0.5 }}>{job.source}</Typography>
                        <Typography variant="caption" display="block" color="text.disabled">{job.date_added}</Typography>
                      </Box>
                    </Box>
                  </Box>
                </Box>
              );
            })}
          </Box>
        )}

        {/* Pagination */}
        {data && data.pages > 1 && (
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", p: 2, borderTop: 1, borderColor: "divider" }}>
            <Typography variant="body2" color="text.secondary">
              Page <strong>{data.page}</strong> of <strong>{data.pages}</strong>
            </Typography>
            <Pagination
              count={data.pages}
              page={page}
              onChange={(_e, p) => {
                const next = new URLSearchParams(searchParams);
                next.set("page", String(p));
                setSearchParams(next);
              }}
              color="primary"
              size="small"
              showFirstButton
              showLastButton
            />
          </Box>
        )}
      </Paper>
    </Box>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <FormControl size="small" fullWidth>
      <InputLabel>{label}</InputLabel>
      <Select
        value={value}
        label={label}
        onChange={(e: SelectChangeEvent) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}

const fmtNum = (n: number | null) =>
  n != null ? n.toLocaleString("pl-PL", { maximumFractionDigits: 0 }) : "?";

function formatSalary(j: Job): { plnLine: string; hourlyLine: string | null; originalLine: string | null } {
  const s = j.salary;
  if (!s || (!s.min && !s.max)) return { plnLine: "\u2014", hourlyLine: null, originalLine: null };

  const cur = s.currency ?? "";
  const periodLabel = s.period === "hourly" ? "/h" : s.period === "daily" ? "/day" : "/mo";
  const originalStr = `${fmtNum(s.min)} - ${fmtNum(s.max)} ${cur}${periodLabel}`;

  if (s.min_pln != null && s.max_pln != null) {
    const plnLine = `${fmtNum(s.min_pln)} - ${fmtNum(s.max_pln)} PLN/mo`;
    const hMin = Math.round(s.min_pln / 160);
    const hMax = Math.round(s.max_pln / 160);
    const hourlyLine = `${fmtNum(hMin)} - ${fmtNum(hMax)} PLN/h`;
    const originalLine = cur !== "PLN" || s.period !== "monthly" ? originalStr : null;
    return { plnLine, hourlyLine, originalLine };
  }

  return { plnLine: originalStr, hourlyLine: null, originalLine: null };
}
