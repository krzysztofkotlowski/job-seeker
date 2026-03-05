import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, LabelList,
  AreaChart, Area,
} from "recharts";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import type { SelectChangeEvent } from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import CircularProgress from "@mui/material/CircularProgress";
import { api } from "../api/client";
import type { AnalyticsData } from "../api/types";

const COLORS = [
  "#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd",
  "#818cf8", "#4f46e5", "#7c3aed", "#5b21b6",
  "#312e81", "#4338ca", "#6d28d9", "#9333ea",
];

const STATUS_COLORS: Record<string, string> = {
  new: "#6366f1",
  seen: "#9ca3af",
  applied: "#0ea5e9",
  interview: "#f59e0b",
  offer: "#22c55e",
  rejected: "#ef4444",
};

const fmt = (n: number | null | undefined) =>
  n != null ? n.toLocaleString("pl-PL", { maximumFractionDigits: 0 }) : "-";

export function DashboardPage() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [seniorities, setSeniorities] = useState<string[]>([]);
  const [selectedSeniority, setSelectedSeniority] = useState("");

  useEffect(() => {
    api.listSeniorities().then(setSeniorities).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    api.analytics({ seniority: selectedSeniority || undefined })
      .then(setData)
      .finally(() => setLoading(false));
  }, [selectedSeniority]);

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }
  if (!data || data.total_jobs === 0) {
    return (
      <Paper sx={{ p: 6, textAlign: "center" }}>
        <Typography color="text.secondary">No data yet. Import some jobs first.</Typography>
      </Paper>
    );
  }

  const appliedCount = data.by_status["applied"] ?? 0;
  const avgSalary =
    data.salary_stats.avg_min_pln && data.salary_stats.avg_max_pln
      ? `${fmt(data.salary_stats.avg_min_pln)} - ${fmt(data.salary_stats.avg_max_pln)}`
      : "-";

  const sourceData = Object.entries(data.by_source).map(([name, value]) => ({ name, value }));
  const statusData = Object.entries(data.by_status).map(([name, value]) => ({ name, value }));

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      {/* Filter */}
      <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel>Filter by Seniority</InputLabel>
          <Select
            value={selectedSeniority}
            label="Filter by Seniority"
            onChange={(e: SelectChangeEvent) => setSelectedSeniority(e.target.value)}
          >
            <MenuItem value="">All Seniorities</MenuItem>
            {seniorities.map((s) => (
              <MenuItem key={s} value={s}>{s}</MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>

      {/* KPI Cards */}
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", md: "1fr 1fr 1fr 1fr" }, gap: 2 }}>
        <KpiCard label="Total Jobs" value={fmt(data.total_jobs)} />
        <KpiCard label="Applied" value={fmt(appliedCount)} color="info.main" />
        <KpiCard label="Avg Salary (PLN/mo)" value={avgSalary} color="success.main" />
        <KpiCard label="Reposted" value={fmt(data.reposted_count)} color="warning.main" />
      </Box>

      {/* Row 1: Source pie + Status pie */}
      <Box sx={{ display: "grid", gridTemplateColumns: { md: "1fr 1fr" }, gap: 3 }}>
        <ChartCard title="Jobs by Source">
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={sourceData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={90}
                label={({ name, value }) => `${name ?? ""} (${value})`}
              >
                {sourceData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Jobs by Status">
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={statusData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={90}
                label={({ name, value }) => `${name} (${value})`}
              >
                {statusData.map((entry) => <Cell key={entry.name} fill={STATUS_COLORS[entry.name] ?? COLORS[0]} />)}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </Box>

      {/* Category bar chart */}
      {data.by_category.length > 0 && (
        <ChartCard title="Jobs by Category">
          <ResponsiveContainer width="100%" height={Math.max(280, data.by_category.length * 28)}>
            <BarChart data={data.by_category} layout="vertical" margin={{ left: 110, right: 40 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" />
              <YAxis type="category" dataKey="category" width={105} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#6366f1" radius={[0, 4, 4, 0]}>
                <LabelList dataKey="count" position="right" style={{ fontSize: 11, fill: "#555" }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      )}

      {/* Salary by category */}
      {data.salary_stats.by_category.length > 0 && (
        <ChartCard title="Average Salary Range by Category (PLN/mo)">
          <ResponsiveContainer width="100%" height={Math.max(280, data.salary_stats.by_category.length * 32)}>
            <BarChart data={data.salary_stats.by_category} layout="vertical" margin={{ left: 110, right: 50 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
              <YAxis type="category" dataKey="category" width={105} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v) => `${fmt(v as number)} PLN`} />
              <Bar dataKey="avg_min" name="Avg Min" fill="#a78bfa" radius={[0, 4, 4, 0]}>
                <LabelList dataKey="avg_min" position="right" formatter={(v) => `${(Number(v) / 1000).toFixed(0)}k`} style={{ fontSize: 10, fill: "#888" }} />
              </Bar>
              <Bar dataKey="avg_max" name="Avg Max" fill="#6366f1" radius={[0, 4, 4, 0]}>
                <LabelList dataKey="avg_max" position="right" formatter={(v) => `${(Number(v) / 1000).toFixed(0)}k`} style={{ fontSize: 10, fill: "#555" }} />
              </Bar>
              <Legend />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      )}

      {/* Seniority (pie, only when no seniority filter) + Work Type */}
      <Box sx={{ display: "grid", gridTemplateColumns: { md: "1fr 1fr" }, gap: 3 }}>
        {!selectedSeniority && data.by_seniority.length > 0 && (
          <ChartCard title="Jobs by Seniority">
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={data.by_seniority}
                  dataKey="count"
                  nameKey="seniority"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  label={(props) => `${props.name ?? ""} (${props.value})`}
                >
                  {data.by_seniority.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </ChartCard>
        )}

        {data.by_work_type.length > 0 && (
          <ChartCard title="Jobs by Work Type">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data.by_work_type}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="work_type" tick={{ fontSize: 12 }} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" fill="#0ea5e9" radius={[4, 4, 0, 0]}>
                  <LabelList dataKey="count" position="top" style={{ fontSize: 11, fill: "#555" }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        )}
      </Box>

      {/* Timeline */}
      {data.added_over_time.length > 1 && (
        <ChartCard title="Jobs Added Over Time">
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={data.added_over_time}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis />
              <Tooltip />
              <Area type="monotone" dataKey="count" stroke="#6366f1" fill="#c4b5fd" fillOpacity={0.5} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>
      )}

      {/* Top companies + Top locations */}
      <Box sx={{ display: "grid", gridTemplateColumns: { md: "1fr 1fr" }, gap: 3 }}>
        {data.top_companies.length > 0 && (
          <ChartCard title="Top Companies">
            <Box sx={{ maxHeight: 320, overflow: "auto" }}>
              {data.top_companies.map((c, i) => (
                <Box key={c.company} sx={{ display: "flex", justifyContent: "space-between", py: 0.75, px: 0.5, borderBottom: 1, borderColor: "divider" }}>
                  <Box sx={{ display: "flex", gap: 1, minWidth: 0 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ width: 24, textAlign: "right", flexShrink: 0 }}>{i + 1}.</Typography>
                    <Typography variant="body2" noWrap>{c.company}</Typography>
                  </Box>
                  <Typography variant="body2" fontWeight={600} sx={{ flexShrink: 0, ml: 1 }}>{c.count}</Typography>
                </Box>
              ))}
            </Box>
          </ChartCard>
        )}

        {data.top_locations.length > 0 && (
          <ChartCard title="Top Locations">
            <Box sx={{ maxHeight: 320, overflow: "auto" }}>
              {data.top_locations.map((l, i) => (
                <Box key={l.location} sx={{ display: "flex", justifyContent: "space-between", py: 0.75, px: 0.5, borderBottom: 1, borderColor: "divider" }}>
                  <Box sx={{ display: "flex", gap: 1, minWidth: 0 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ width: 24, textAlign: "right", flexShrink: 0 }}>{i + 1}.</Typography>
                    <Typography variant="body2" noWrap>{l.location}</Typography>
                  </Box>
                  <Typography variant="body2" fontWeight={600} sx={{ flexShrink: 0, ml: 1 }}>{l.count}</Typography>
                </Box>
              ))}
            </Box>
          </ChartCard>
        )}
      </Box>
    </Box>
  );
}

function KpiCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <Paper sx={{ p: 2.5 }}>
      <Typography variant="overline" color="text.secondary" fontSize={11}>{label}</Typography>
      <Typography variant="h5" fontWeight={700} sx={{ color: color ?? "text.primary", mt: 0.5 }}>{value}</Typography>
    </Paper>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Paper sx={{ p: 3 }}>
      <Typography variant="subtitle2" fontWeight={600} color="text.secondary" sx={{ mb: 2 }}>{title}</Typography>
      {children}
    </Paper>
  );
}
