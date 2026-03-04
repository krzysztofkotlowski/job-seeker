import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import type { SelectChangeEvent } from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import Pagination from "@mui/material/Pagination";
import CircularProgress from "@mui/material/CircularProgress";
import LinearProgress from "@mui/material/LinearProgress";
import { api } from "../api/client";
import type { SkillsSummary } from "../api/types";

const PER_PAGE = 50;

export function SkillsPage() {
  const [data, setData] = useState<SkillsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [categories, setCategories] = useState<string[]>([]);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    api.listCategories().then(setCategories).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    api
      .skillsSummary({ per_page: PER_PAGE, page, category: selectedCategory || undefined })
      .then(setData)
      .finally(() => setLoading(false));
  }, [selectedCategory, page]);

  const handleCategoryChange = (e: SelectChangeEvent) => {
    setSelectedCategory(e.target.value);
    setPage(1);
  };

  if (loading && !data) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!data || data.total_jobs === 0) {
    return (
      <Paper sx={{ p: 6, textAlign: "center" }}>
        <Typography color="text.secondary">No skills data yet. Import some jobs first.</Typography>
      </Paper>
    );
  }

  const maxCount = data.top_skills[0]?.count ?? 1;

  return (
    <Paper sx={{ p: 3 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 3 }}>
        <Box>
          <Typography variant="h6" fontWeight={600}>Skills Overview</Typography>
          <Typography variant="body2" color="text.secondary">
            {data.total_skills.toLocaleString()} skills across {data.total_jobs.toLocaleString()} job{data.total_jobs !== 1 ? "s" : ""}
            {selectedCategory ? ` in ${selectedCategory}` : ""}
          </Typography>
        </Box>
        {categories.length > 0 && (
          <FormControl size="small" sx={{ minWidth: 180 }}>
            <InputLabel>Category</InputLabel>
            <Select
              value={selectedCategory}
              label="Category"
              onChange={handleCategoryChange}
            >
              <MenuItem value="">All Categories</MenuItem>
              {categories.map((c) => (
                <MenuItem key={c} value={c}>{c}</MenuItem>
              ))}
            </Select>
          </FormControl>
        )}
      </Box>

      <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
        {data.top_skills.map((item) => {
          const pct = Math.round((item.count / maxCount) * 100);
          const reqPct = item.required_count ? Math.round((item.required_count / maxCount) * 100) : 0;
          return (
            <Box key={item.skill}>
              <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 0.5 }}>
                <Typography variant="body2" fontWeight={500}>{item.skill}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {item.count} job{item.count !== 1 ? "s" : ""}
                  {item.required_count ? ` (${item.required_count} required)` : ""}
                </Typography>
              </Box>
              <Box sx={{ position: "relative", height: 12, borderRadius: 1, overflow: "hidden", bgcolor: "grey.100" }}>
                <LinearProgress
                  variant="determinate"
                  value={pct}
                  sx={{
                    position: "absolute",
                    inset: 0,
                    height: "100%",
                    borderRadius: 1,
                    bgcolor: "transparent",
                    "& .MuiLinearProgress-bar": { bgcolor: "primary.light", borderRadius: 1 },
                  }}
                />
                {reqPct > 0 && (
                  <LinearProgress
                    variant="determinate"
                    value={reqPct}
                    sx={{
                      position: "absolute",
                      inset: 0,
                      height: "100%",
                      borderRadius: 1,
                      bgcolor: "transparent",
                      "& .MuiLinearProgress-bar": { bgcolor: "primary.main", borderRadius: 1 },
                    }}
                  />
                )}
              </Box>
            </Box>
          );
        })}
      </Box>

      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mt: 3, pt: 2, borderTop: 1, borderColor: "divider" }}>
        <Box sx={{ display: "flex", gap: 3 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
            <Box sx={{ width: 12, height: 12, borderRadius: "50%", bgcolor: "primary.main" }} />
            <Typography variant="caption" color="text.secondary">Required</Typography>
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
            <Box sx={{ width: 12, height: 12, borderRadius: "50%", bgcolor: "primary.light" }} />
            <Typography variant="caption" color="text.secondary">Nice to have</Typography>
          </Box>
        </Box>
        {data.pages > 1 && (
          <Pagination
            count={data.pages}
            page={page}
            onChange={(_e, p) => setPage(p)}
            color="primary"
            size="small"
          />
        )}
      </Box>
    </Paper>
  );
}
