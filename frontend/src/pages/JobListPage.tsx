import { useEffect, useState } from "react";
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
import Checkbox from "@mui/material/Checkbox";
import ListItemText from "@mui/material/ListItemText";
import OutlinedInput from "@mui/material/OutlinedInput";
import FormControlLabel from "@mui/material/FormControlLabel";
import Pagination from "@mui/material/Pagination";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Fade from "@mui/material/Fade";
import Autocomplete from "@mui/material/Autocomplete";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Badge from "@mui/material/Badge";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import SearchIcon from "@mui/icons-material/Search";
import FilterListIcon from "@mui/icons-material/FilterList";
import AddIcon from "@mui/icons-material/Add";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import FileCopyOutlinedIcon from "@mui/icons-material/FileCopyOutlined";
import BookmarkIcon from "@mui/icons-material/Bookmark";
import BookmarkBorderIcon from "@mui/icons-material/BookmarkBorder";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useJobsList, useJobsAnalytics, useJobsFilters, jobsKeys } from "../hooks/useJobs";
import { AddJobForm } from "../components/AddJobForm";
import { EmptyState } from "../components/EmptyState";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../contexts/useToast";
import { formatSalary, STATUS_TAB_COLORS } from "../utils/job";

const STATUS_TABS = [
  { value: "", label: "All" },
  { value: "new", label: "New" },
  { value: "seen", label: "Seen" },
  { value: "applied", label: "Applied" },
  { value: "interview", label: "Interview" },
  { value: "offer", label: "Offer" },
  { value: "rejected", label: "Rejected" },
] as const;

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
const FILTER_STORAGE_KEY = "job-list-filters";

export function JobListPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [showFilters, setShowFilters] = useState(true);
  const [filtersRestored, setFiltersRestored] = useState(false);
  const [readyToFetch, setReadyToFetch] = useState(false);
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [addJobOpen, setAddJobOpen] = useState(false);

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
  const seniorityArr = seniority ? seniority.split(",") : [];
  const skillsParam =
    searchParams.get("skills") || searchParams.get("skill") || "";
  const skillsArr = skillsParam
    ? skillsParam
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
    : [];
  const savedFilter = searchParams.get("saved") || "";
  const showDuplicates = searchParams.get("group_duplicates") === "true";

  const savedBool =
    savedFilter === "true" ? true : savedFilter === "false" ? false : undefined;
  const repostedBool =
    reposted === "true" ? true : reposted === "false" ? false : undefined;

  const filtersQuery = useJobsFilters();
  const workTypes = filtersQuery.data?.workTypes ?? [];
  const locations = filtersQuery.data?.locations ?? [];
  const categories = filtersQuery.data?.categories ?? [];
  const seniorities = filtersQuery.data?.seniorities ?? [];
  const topSkills = filtersQuery.data?.topSkills ?? [];

  useEffect(() => {
    if (filtersQuery.isError && filtersQuery.error) {
      toast.showError(
        filtersQuery.error instanceof Error
          ? filtersQuery.error.message
          : "Failed to load filter options",
      );
    }
  }, [filtersQuery.isError, filtersQuery.error, toast]);

  const jobsQuery = useJobsList({
    page,
    perPage: PER_PAGE,
    status: status || undefined,
    source: source || undefined,
    category: category || undefined,
    seniority: seniority || undefined,
    skills: skillsParam || undefined,
    search: search || undefined,
    isReposted: repostedBool,
    workType: workType || undefined,
    location: location || undefined,
    sortBy: sortBy || undefined,
    groupDuplicates: !showDuplicates,
    saved: savedBool,
    enabled: readyToFetch,
  });

  const analyticsQuery = useJobsAnalytics({
    source: source || undefined,
    category: category || undefined,
    seniority: seniority || undefined,
    skills: skillsParam || undefined,
    search: debouncedSearch || undefined,
    isReposted: repostedBool,
    workType: workType || undefined,
    location: location || undefined,
    saved: savedBool,
    groupDuplicates: !showDuplicates,
    enabled: readyToFetch,
  });

  const data = jobsQuery.data ?? null;
  const loading = jobsQuery.isLoading;
  const counts = analyticsQuery.data
    ? {
        by_status: analyticsQuery.data.by_status,
        saved_count: analyticsQuery.data.saved_count ?? 0,
      }
    : null;

  useEffect(() => {
    if (jobsQuery.isError && jobsQuery.error) {
      toast.showError(
        jobsQuery.error instanceof Error
          ? jobsQuery.error.message
          : "Failed to load jobs",
      );
    }
  }, [jobsQuery.isError, jobsQuery.error, toast]);

  useEffect(() => {
    if (analyticsQuery.isError && analyticsQuery.error) {
      toast.showError(
        analyticsQuery.error instanceof Error
          ? analyticsQuery.error.message
          : "Failed to load analytics",
      );
    }
  }, [analyticsQuery.isError, analyticsQuery.error, toast]);

  // Debounce search for analytics to avoid a request on every keystroke
  useEffect(() => {
    queueMicrotask(() =>
      setDebouncedSearch((prev) => (prev === "" && search ? search : prev)),
    );
    const t = setTimeout(() => setDebouncedSearch(search), 400);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    if (filtersRestored) return;
    const keys = [...searchParams.keys()].filter((k) => k !== "page");
    if (keys.length > 0) {
      queueMicrotask(() => {
        setFiltersRestored(true);
        setReadyToFetch(true);
      });
      return;
    }
    queueMicrotask(() => {
      setFiltersRestored(true);
      setReadyToFetch(true);
    });
    try {
      const saved = localStorage.getItem(FILTER_STORAGE_KEY);
      if (saved) {
        const parsed = new URLSearchParams(saved);
        if (parsed.toString()) setSearchParams(parsed);
      }
    } catch {
      // ignore
    }
  }, [filtersRestored, searchParams, setSearchParams]);

  useEffect(() => {
    const qs = searchParams.toString();
    if (qs) localStorage.setItem(FILTER_STORAGE_KEY, qs);
  }, [searchParams]);

  const refetchJobs = () => {
    queryClient.invalidateQueries({ queryKey: jobsKeys.all });
  };

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

  const setStatusAndSaved = (newStatus: string, newSaved: string) => {
    const next = new URLSearchParams(searchParams);
    if (newStatus) next.set("status", newStatus);
    else next.delete("status");
    if (newSaved) next.set("saved", newSaved);
    else next.delete("saved");
    next.set("page", "1");
    setSearchParams(next);
  };

  const clearFilters = () => {
    setSearchParams({ page: "1" });
  };

  const activeFilters: { key: string; label: string }[] = [];
  if (source) activeFilters.push({ key: "source", label: `Source: ${source}` });
  if (category)
    activeFilters.push({ key: "category", label: `Category: ${category}` });
  if (seniority) {
    seniorityArr.forEach((s) =>
      activeFilters.push({ key: `seniority:${s}`, label: `Seniority: ${s}` }),
    );
  }
  if (workType)
    activeFilters.push({ key: "work_type", label: `Work: ${workType}` });
  if (location)
    activeFilters.push({ key: "location", label: `Location: ${location}` });
  skillsArr.forEach((s) =>
    activeFilters.push({ key: `skill:${s}`, label: `Skill: ${s}` }),
  );
  if (reposted)
    activeFilters.push({
      key: "is_reposted",
      label: reposted === "true" ? "Reposted" : "Original",
    });
  if (showDuplicates)
    activeFilters.push({ key: "group_duplicates", label: "Show duplicates" });
  if (sortBy)
    activeFilters.push({
      key: "sort_by",
      label: `Sort: ${SORT_OPTIONS.find((o) => o.value === sortBy)?.label ?? sortBy}`,
    });

  const jobs = data?.items ?? [];

  const handleSearch = async (value: string) => {
    const trimmed = value.trim();
    if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
      try {
        const result = await api.findByUrl(trimmed);
        navigate(`/jobs/${result.id}`);
        return;
      } catch {
        // URL not found in DB -- fall through to normal search
      }
    }
    setFilter("search", trimmed);
  };

  const handleToggleSaved = async (
    e: React.MouseEvent,
    jobId: string,
    current: boolean,
  ) => {
    e.stopPropagation();
    try {
      await api.updateJob(jobId, { saved: !current });
      refetchJobs();
    } catch (err) {
      toast.showError(
        err instanceof Error ? err.message : "Failed to update saved status",
      );
    }
  };

  const handleMarkSeen = async (e: React.MouseEvent, jobId: string) => {
    e.stopPropagation();
    try {
      await api.updateJob(jobId, { status: "seen" });
      refetchJobs();
    } catch (err) {
      toast.showError(
        err instanceof Error ? err.message : "Failed to mark as seen",
      );
    }
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {/* Header */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 1,
        }}
      >
        <Typography variant="body2" color="text.secondary">
          {data ? (
            <>
              <strong>{data.total.toLocaleString()}</strong> job
              {data.total !== 1 ? "s" : ""} found
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
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setAddJobOpen(true)}
          >
            Add Job
          </Button>
          <Button
            size="small"
            variant="outlined"
            startIcon={<FilterListIcon />}
            onClick={() => setShowFilters((v) => !v)}
          >
            Filters
            {activeFilters.length > 0 && (
              <Chip
                label={activeFilters.length}
                size="small"
                color="primary"
                sx={{ ml: 1, height: 20, fontSize: 11 }}
              />
            )}
          </Button>
        </Box>
      </Box>

      <Dialog
        open={addJobOpen}
        onClose={() => setAddJobOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Add Job Offer</DialogTitle>
        <DialogContent>
          <AddJobForm
            onJobAdded={() => {
              setAddJobOpen(false);
              refetchJobs();
            }}
          />
        </DialogContent>
      </Dialog>

      <Paper
        elevation={0}
        sx={{
          border: 1,
          borderColor: "divider",
          borderRadius: 2,
          overflow: "hidden",
        }}
      >
        {/* Search */}
        <Box sx={{ p: 2, borderBottom: 1, borderColor: "divider" }}>
          <TextField
            fullWidth
            size="small"
            defaultValue={search}
            onKeyDown={(e) => {
              if (e.key === "Enter")
                handleSearch((e.target as HTMLInputElement).value);
            }}
            onBlur={(e) => handleSearch(e.target.value)}
            placeholder="Search by title, company, or paste offer URL..."
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

        {/* Status & Saved tabs with counts (even width, larger chips) */}
        <Box
          sx={{
            px: 2,
            py: 1.5,
            borderBottom: 1,
            borderColor: "divider",
            display: "flex",
            flexWrap: { xs: "wrap", sm: "nowrap" },
            gap: 0.5,
            alignItems: "stretch",
          }}
        >
          <Tooltip
            title="Total postings (includes duplicates). List groups duplicates by default; enable below to see each posting."
            arrow
          >
            <Chip
              label={
                counts
                  ? `All (${counts.by_status ? Object.values(counts.by_status).reduce((a, b) => a + b, 0) : 0})`
                  : "All"
              }
              onClick={() => setStatusAndSaved("", "")}
              variant={!status && !savedFilter ? "filled" : "outlined"}
              color="primary"
              sx={{
                flex: 1,
                minWidth: 0,
                fontWeight: 600,
                height: 40,
                fontSize: "0.875rem",
                "& .MuiChip-label": { px: 1 },
              }}
            />
          </Tooltip>
          {STATUS_TABS.filter((t) => t.value !== "").map((tab) => {
            const count = counts?.by_status?.[tab.value] ?? 0;
            const selected = status === tab.value && !savedFilter;
            return (
              <Chip
                key={tab.value}
                label={`${tab.label} (${count})`}
                onClick={() => setStatusAndSaved(tab.value, "")}
                variant={selected ? "filled" : "outlined"}
                sx={{
                  flex: 1,
                  minWidth: 0,
                  fontWeight: selected ? 600 : 500,
                  height: 40,
                  fontSize: "0.875rem",
                  "& .MuiChip-label": { px: 1 },
                  ...(selected && tab.value && STATUS_TAB_COLORS[tab.value]
                    ? {
                        bgcolor: STATUS_TAB_COLORS[tab.value],
                        color: "white",
                        borderColor: STATUS_TAB_COLORS[tab.value],
                        "&:hover": { bgcolor: STATUS_TAB_COLORS[tab.value] },
                      }
                    : {}),
                  ...(!selected && tab.value && STATUS_TAB_COLORS[tab.value]
                    ? {
                        borderColor: STATUS_TAB_COLORS[tab.value],
                        color: STATUS_TAB_COLORS[tab.value],
                      }
                    : {}),
                }}
              />
            );
          })}
          <Chip
            label={counts ? `Saved (${counts.saved_count})` : "Saved"}
            onClick={() => setStatusAndSaved("", "true")}
            variant={savedFilter === "true" ? "filled" : "outlined"}
            color="secondary"
            sx={{
              flex: 1,
              minWidth: 0,
              fontWeight: savedFilter === "true" ? 600 : 500,
              height: 40,
              fontSize: "0.875rem",
              "& .MuiChip-label": { px: 1 },
            }}
          />
        </Box>

        {/* Filters */}
        <Collapse in={showFilters}>
          <Box
            sx={{
              px: 2,
              py: 1.5,
              borderBottom: 1,
              borderColor: "divider",
              bgcolor: "action.hover",
            }}
          >
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: {
                  xs: "1fr",
                  sm: "1fr 1fr",
                  md: "1fr 1fr 1fr 1fr",
                  lg: "repeat(4, 1fr)",
                },
                gap: 1.5,
              }}
            >
              <FilterSelect
                label="Source"
                value={source}
                onChange={(v) => setFilter("source", v)}
                options={SOURCE_OPTIONS}
              />
              <FilterSelect
                label="Category"
                value={category}
                onChange={(v) => setFilter("category", v)}
                options={[
                  { value: "", label: "All Categories" },
                  ...categories.map((c) => ({ value: c, label: c })),
                ]}
              />
              <FormControl size="small" fullWidth>
                <InputLabel>Seniority</InputLabel>
                <Select<string[]>
                  multiple
                  value={seniorityArr}
                  onChange={(e) => {
                    const val = e.target.value;
                    setFilter(
                      "seniority",
                      (typeof val === "string" ? val.split(",") : val).join(
                        ",",
                      ),
                    );
                  }}
                  input={<OutlinedInput label="Seniority" />}
                  renderValue={(sel) => (sel as string[]).join(", ")}
                >
                  {seniorities.map((s) => (
                    <MenuItem key={s} value={s}>
                      <Checkbox
                        size="small"
                        checked={seniorityArr.includes(s)}
                      />
                      <ListItemText primary={s} />
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FilterSelect
                label="Work Type"
                value={workType}
                onChange={(v) => setFilter("work_type", v)}
                options={[
                  { value: "", label: "All Work Types" },
                  ...workTypes.map((wt) => ({ value: wt, label: wt })),
                ]}
              />
            </Box>
            <Box
              sx={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 1.5,
                mt: 1.5,
              }}
            >
              <FilterSelect
                label="Location"
                value={location}
                onChange={(v) => setFilter("location", v)}
                options={[
                  { value: "", label: "All Locations" },
                  ...locations.map((loc) => ({ value: loc, label: loc })),
                ]}
                sx={{ minWidth: { xs: 0, sm: 140 } }}
              />
              <FilterSelect
                label="Reposted"
                value={reposted}
                onChange={(v) => setFilter("is_reposted", v)}
                options={REPOSTED_OPTIONS}
                sx={{ minWidth: { xs: 0, sm: 130 } }}
              />
              <Box sx={{ flex: 1, minWidth: { xs: 0, sm: 200 } }}>
                <Autocomplete
                  size="small"
                  multiple
                  freeSolo
                  options={topSkills}
                  value={skillsArr}
                  onChange={(_e, val) =>
                    setFilter("skills", (val as string[]).join(","))
                  }
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Skills (all must match)"
                      placeholder="Add skills…"
                    />
                  )}
                  renderTags={(value, getTagProps) =>
                    value.map((option, index) => (
                      <Chip
                        {...getTagProps({ index })}
                        key={option}
                        label={option}
                        size="small"
                        variant="outlined"
                      />
                    ))
                  }
                />
              </Box>
              <FormControlLabel
                control={
                  <Checkbox
                    size="small"
                    checked={showDuplicates}
                    onChange={(_e, checked) =>
                      setFilter("group_duplicates", checked ? "true" : "")
                    }
                  />
                }
                label={
                  <Typography variant="caption" color="text.secondary">
                    Show duplicates (list shows one per job by default)
                  </Typography>
                }
                sx={{ mt: 0.5 }}
              />
              <Box sx={{ ml: "auto", minWidth: { xs: 0, sm: 180 } }}>
                <FilterSelect
                  label="Sort By"
                  value={sortBy}
                  onChange={(v) => setFilter("sort_by", v)}
                  options={SORT_OPTIONS}
                />
              </Box>
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
                      onDelete={() => {
                        if (f.key.startsWith("seniority:")) {
                          const toRemove = f.key.split(":")[1];
                          const remaining = seniorityArr.filter(
                            (s) => s !== toRemove,
                          );
                          setFilter("seniority", remaining.join(","));
                        } else if (f.key.startsWith("skill:")) {
                          const toRemove = f.key.slice(6);
                          const remaining = skillsArr.filter(
                            (s) => s !== toRemove,
                          );
                          setFilter("skills", remaining.join(","));
                        } else if (f.key === "group_duplicates") {
                          setFilter("group_duplicates", "");
                        } else {
                          setFilter(f.key, "");
                        }
                      }}
                    />
                  ))}
                </Box>
              </>
            )}
          </Box>
        </Collapse>

        {/* Content */}
        {loading ? (
          <Fade in>
            <LoadingSpinner size={32} message="Loading jobs..." />
          </Fade>
        ) : jobs.length === 0 ? (
          <Fade in>
            <Box sx={{ py: 8 }}>
              <EmptyState
                message="No jobs found"
                description="Try changing filters or importing jobs first"
              />
            </Box>
          </Fade>
        ) : (
          <Fade in>
            <Box sx={{ transition: "opacity 0.2s ease" }}>
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
                        "&:hover": { bgcolor: "action.hover" },
                        transition: "background 0.15s, opacity 0.15s",
                        ...(job.status === "seen" && {
                          opacity: 0.55,
                          bgcolor: "action.hover",
                        }),
                      }}
                    >
                      <Box
                        sx={{
                          display: "flex",
                          flexDirection: { xs: "column", sm: "row" },
                          justifyContent: "space-between",
                          gap: 2,
                        }}
                      >
                        <Box sx={{ minWidth: 0, flex: 1 }}>
                          <Box
                            sx={{
                              display: "flex",
                              alignItems: "center",
                              flexWrap: "wrap",
                              gap: 1,
                              mb: 0.5,
                            }}
                          >
                            <Typography
                              variant="h6"
                              sx={{
                                fontWeight: 700,
                                fontSize: "1.1rem",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: { xs: "normal", sm: "nowrap" },
                                wordBreak: { xs: "break-word", sm: "normal" },
                              }}
                            >
                              {job.title}
                            </Typography>
                            <StatusBadge status={job.status} />
                            {job.saved && (
                              <Chip
                                label="Saved"
                                size="small"
                                color="primary"
                                variant="filled"
                                sx={{ height: 20, fontSize: 11 }}
                              />
                            )}
                            {job.is_reposted && (
                              <Chip
                                label="Reposted"
                                size="small"
                                color="warning"
                                variant="outlined"
                                sx={{ height: 20, fontSize: 11 }}
                              />
                            )}
                            {(job.duplicate_count ?? 1) > 1 && (
                              <Tooltip
                                title={`${job.duplicate_count} duplicate postings of this position`}
                              >
                                <Badge
                                  badgeContent={job.duplicate_count}
                                  color="secondary"
                                  max={99}
                                  sx={{
                                    "& .MuiBadge-badge": {
                                      fontSize: 10,
                                      height: 18,
                                      minWidth: 18,
                                    },
                                  }}
                                >
                                  <FileCopyOutlinedIcon
                                    sx={{
                                      fontSize: 20,
                                      color: "text.secondary",
                                    }}
                                  />
                                </Badge>
                              </Tooltip>
                            )}
                          </Box>
                          <Typography
                            variant="subtitle1"
                            fontWeight={600}
                            color="text.primary"
                          >
                            {job.company}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            {job.location.join(", ") || "No location"}
                            {job.work_type ? ` · ${job.work_type}` : ""}
                            {job.category ? ` · ${job.category}` : ""}
                            {job.seniority ? ` · ${job.seniority}` : ""}
                          </Typography>
                          <Box
                            sx={{
                              display: "flex",
                              flexWrap: "wrap",
                              gap: 0.5,
                              mt: 1,
                            }}
                          >
                            {job.skills_required.slice(0, 6).map((s) => (
                              <Chip
                                key={s}
                                label={s}
                                size="small"
                                variant="outlined"
                                color="primary"
                                sx={{ height: 22, fontSize: 11 }}
                              />
                            ))}
                            {job.skills_required.length > 6 && (
                              <Typography
                                variant="caption"
                                color="text.secondary"
                              >
                                +{job.skills_required.length - 6} more
                              </Typography>
                            )}
                          </Box>
                          {(job.detected_skills?.length ?? 0) > 0 && (
                            <Box
                              sx={{
                                display: "flex",
                                flexWrap: "wrap",
                                gap: 0.5,
                                mt: 0.5,
                              }}
                            >
                              <Typography
                                variant="caption"
                                color="text.secondary"
                                sx={{ lineHeight: "22px", mr: 0.25 }}
                              >
                                Detected:
                              </Typography>
                              {job.detected_skills!.slice(0, 5).map((s) => (
                                <Chip
                                  key={s}
                                  label={s}
                                  size="small"
                                  variant="outlined"
                                  color="success"
                                  sx={{ height: 22, fontSize: 11 }}
                                />
                              ))}
                              {job.detected_skills!.length > 5 && (
                                <Typography
                                  variant="caption"
                                  color="text.secondary"
                                >
                                  +{job.detected_skills!.length - 5} more
                                </Typography>
                              )}
                            </Box>
                          )}
                        </Box>
                        <Box
                          sx={{
                            flexShrink: 0,
                            display: "flex",
                            flexDirection: { xs: "row", sm: "row" },
                            alignItems: { xs: "flex-start", sm: "center" },
                            gap: 1.5,
                          }}
                        >
                          <Box sx={{ textAlign: "right" }}>
                            <Typography
                              variant="body2"
                              fontWeight={700}
                              color="success.dark"
                            >
                              {sal.plnLine}
                            </Typography>
                            {sal.hourlyLine && (
                              <Typography
                                variant="caption"
                                color="text.secondary"
                              >
                                {sal.hourlyLine}
                              </Typography>
                            )}
                            {sal.originalLine && (
                              <Typography
                                variant="caption"
                                display="block"
                                color="text.disabled"
                                sx={{ mt: 0.25 }}
                              >
                                {sal.originalLine}
                              </Typography>
                            )}
                            <Typography
                              variant="caption"
                              display="block"
                              color="text.disabled"
                              sx={{ mt: 0.5 }}
                            >
                              {job.source}
                            </Typography>
                            <Typography
                              variant="caption"
                              display="block"
                              color="text.disabled"
                            >
                              {job.date_added}
                            </Typography>
                          </Box>
                          <Tooltip
                            title={
                              job.saved ? "Remove from saved" : "Save for later"
                            }
                            arrow
                          >
                            <IconButton
                              onClick={(e) =>
                                handleToggleSaved(e, job.id, !!job.saved)
                              }
                              color={job.saved ? "primary" : "default"}
                              sx={{
                                border: 1,
                                borderColor: "divider",
                                width: 40,
                                height: 40,
                              }}
                            >
                              {job.saved ? (
                                <BookmarkIcon />
                              ) : (
                                <BookmarkBorderIcon />
                              )}
                            </IconButton>
                          </Tooltip>
                          {job.status === "new" && (
                            <Tooltip title="Mark as Seen" arrow>
                              <IconButton
                                onClick={(e) => handleMarkSeen(e, job.id)}
                                color="default"
                                sx={{
                                  border: 1,
                                  borderColor: "divider",
                                  width: 40,
                                  height: 40,
                                }}
                              >
                                <VisibilityOffIcon />
                              </IconButton>
                            </Tooltip>
                          )}
                        </Box>
                      </Box>
                    </Box>
                  </Box>
                );
              })}
            </Box>
          </Fade>
        )}

        {/* Pagination */}
        {data && data.pages > 1 && (
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              p: 2,
              borderTop: 1,
              borderColor: "divider",
            }}
          >
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
  sx,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  sx?: object;
}) {
  return (
    <FormControl size="small" fullWidth sx={sx}>
      <InputLabel>{label}</InputLabel>
      <Select
        value={value}
        label={label}
        onChange={(e: SelectChangeEvent) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <MenuItem key={o.value} value={o.value}>
            {o.label}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
