import type { ComponentProps } from "react";
import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
  LabelList,
  AreaChart,
  Area,
} from "recharts";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import type { SelectChangeEvent } from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import { useTheme } from "@mui/material/styles";
import { ChartTooltip } from "../components/ChartTooltip";
import { EmptyState } from "../components/EmptyState";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { api } from "../api/client";
import type { AnalyticsData, SalaryCategoryStat } from "../api/types";
import { useToast } from "../contexts/useToast";
import { STATUS_TAB_COLORS } from "../utils/job";

const fmt = (n: number | null | undefined) =>
  n != null ? n.toLocaleString("pl-PL", { maximumFractionDigits: 0 }) : "-";

/** Range bar chart: each bar spans from avg_min to avg_max for readability. */
function SalaryRangeChart({ data }: { data: SalaryCategoryStat[] }) {
  const theme = useTheme();
  const labelColor =
    theme.palette.mode === "dark"
      ? theme.palette.grey[100]
      : theme.palette.common.white;

  const chartData = data.map((d) => {
    const min = d.avg_min ?? 0;
    const max = d.avg_max ?? min;
    return {
      ...d,
      rangeMin: min,
      rangeSpan: Math.max(0, max - min),
    };
  });

  return (
    <ResponsiveContainer
      width="100%"
      height={Math.max(280, chartData.length * 32)}
    >
      <BarChart
        data={chartData}
        layout="vertical"
        margin={{ top: 24, left: 110, right: 50, bottom: 24 }}
      >
        <defs>
          <linearGradient
            id="salaryRangeGradient"
            x1="0"
            y1="0"
            x2="1"
            y2="0"
          >
            <stop offset="0%" stopColor="#a78bfa" />
            <stop offset="100%" stopColor="#6366f1" />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          type="number"
          tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
        />
        <YAxis
          type="category"
          dataKey="category"
          width={105}
          tick={{ fontSize: 12 }}
        />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const p = payload[0]?.payload as (typeof chartData)[number];
            if (!p) return null;
            return (
              <ChartTooltip
                active
                payload={[
                  {
                    name: "",
                    value: `${fmt(p.avg_min)} - ${fmt(p.avg_max)} PLN/mo`,
                  },
                ]}
                label={p.category}
              />
            );
          }}
          contentStyle={{
            background: "transparent",
            border: "none",
            padding: 0,
          }}
        />
        <Bar
          dataKey="rangeMin"
          stackId="salary"
          fill="transparent"
          isAnimationActive={false}
        />
        <Bar
          dataKey="rangeSpan"
          stackId="salary"
          fill="url(#salaryRangeGradient)"
          radius={8}
        >
          <LabelList
            dataKey="rangeSpan"
            position="right"
            content={((props: Record<string, unknown>) => {
              const p = props.payload as SalaryCategoryStat | undefined;
              const datum = p ?? chartData[(props.index as number) ?? 0];
              const min = datum?.avg_min ?? 0;
              const max = datum?.avg_max ?? min;
              const text =
                min !== max
                  ? `${(min / 1000).toFixed(0)}k - ${(max / 1000).toFixed(0)}k`
                  : `${(max / 1000).toFixed(0)}k`;
              const xVal = Number(props.x) || 0;
              return (
                <text
                  x={xVal + 6}
                  y={props.y as number}
                  textAnchor="start"
                  dominantBaseline="middle"
                  style={{ fontSize: 13, fontWeight: 600, fill: labelColor }}
                >
                  {text}
                </text>
              );
            }) as never}
            style={{ fontSize: 13, fontWeight: 600, fill: labelColor }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

const COLORS = [
  "#6366f1",
  "#8b5cf6",
  "#a78bfa",
  "#c4b5fd",
  "#818cf8",
  "#4f46e5",
  "#7c3aed",
  "#5b21b6",
  "#312e81",
  "#4338ca",
  "#6d28d9",
  "#9333ea",
];

export function DashboardPage() {
  const toast = useToast();
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [seniorities, setSeniorities] = useState<string[]>([]);
  const [selectedSeniority, setSelectedSeniority] = useState("");
  const [uniqueOffers, setUniqueOffers] = useState(false);

  useEffect(() => {
    api
      .listSeniorities()
      .then(setSeniorities)
      .catch((e) =>
        toast.showError(
          e instanceof Error ? e.message : "Failed to load seniorities",
        ),
      );
  }, [toast]);

  useEffect(() => {
    queueMicrotask(() => setLoading(true));
    api
      .analytics({
        seniority: selectedSeniority || undefined,
        group_duplicates: uniqueOffers,
      })
      .then(setData)
      .catch((e) =>
        toast.showError(
          e instanceof Error ? e.message : "Failed to load analytics",
        ),
      )
      .finally(() => setLoading(false));
  }, [selectedSeniority, uniqueOffers, toast]);

  if (loading) {
    return <LoadingSpinner />;
  }
  if (!data || data.total_jobs === 0) {
    return (
      <Paper sx={{ p: 6 }}>
        <EmptyState
          message="No data yet."
          description="Import some jobs first."
        />
      </Paper>
    );
  }

  const appliedCount = data.by_status["applied"] ?? 0;
  const avgSalary =
    data.salary_stats.avg_min_pln && data.salary_stats.avg_max_pln
      ? `${fmt(data.salary_stats.avg_min_pln)} - ${fmt(data.salary_stats.avg_max_pln)}`
      : "-";

  const sourceData = Object.entries(data.by_source).map(([name, value]) => ({
    name,
    value,
  }));
  const statusData = Object.entries(data.by_status).map(([name, value]) => ({
    name,
    value,
  }));

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      {/* Filters */}
      <Box
        sx={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: 2,
          justifyContent: "flex-end",
        }}
      >
        <FormControlLabel
          control={
            <Switch
              checked={uniqueOffers}
              onChange={(e) => setUniqueOffers(e.target.checked)}
              color="primary"
            />
          }
          label="Unique offers only (deduplicate by company + title)"
        />
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel>Filter by Seniority</InputLabel>
          <Select
            value={selectedSeniority}
            label="Filter by Seniority"
            onChange={(e: SelectChangeEvent) =>
              setSelectedSeniority(e.target.value)
            }
          >
            <MenuItem value="">All Seniorities</MenuItem>
            {seniorities.map((s) => (
              <MenuItem key={s} value={s}>
                {s}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>

      {/* KPI Cards */}
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr 1fr", md: "1fr 1fr 1fr 1fr" },
          gap: 2,
        }}
      >
        <KpiCard label="Total Jobs" value={fmt(data.total_jobs)} />
        <KpiCard label="Applied" value={fmt(appliedCount)} color="info.main" />
        <KpiCard
          label="Avg Salary (PLN/mo)"
          value={avgSalary}
          color="success.main"
        />
        <KpiCard
          label="Reposted"
          value={fmt(data.reposted_count)}
          color="warning.main"
        />
      </Box>

      {/* Row 1: Source pie + Status pie */}
      <Box
        sx={{ display: "grid", gridTemplateColumns: { md: "1fr 1fr" }, gap: 3 }}
      >
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
                {sourceData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                content={(props) => <ChartTooltip {...(props as ComponentProps<typeof ChartTooltip>)} />}
                contentStyle={{
                  background: "transparent",
                  border: "none",
                  padding: 0,
                }}
              />
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
                {statusData.map((entry) => (
                  <Cell
                    key={entry.name}
                    fill={STATUS_TAB_COLORS[entry.name] ?? COLORS[0]}
                  />
                ))}
              </Pie>
              <Tooltip
                content={(props) => <ChartTooltip {...(props as ComponentProps<typeof ChartTooltip>)} />}
                contentStyle={{
                  background: "transparent",
                  border: "none",
                  padding: 0,
                }}
              />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </Box>

      {/* Category bar chart */}
      {data.by_category.length > 0 && (
        <ChartCard title="Jobs by Category">
          <ResponsiveContainer
            width="100%"
            height={Math.max(280, data.by_category.length * 28)}
          >
            <BarChart
              data={data.by_category}
              layout="vertical"
              margin={{ left: 110, right: 40 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" />
              <YAxis
                type="category"
                dataKey="category"
                width={105}
                tick={{ fontSize: 12 }}
              />
              <Tooltip
                content={(props) => <ChartTooltip {...(props as ComponentProps<typeof ChartTooltip>)} />}
                contentStyle={{
                  background: "transparent",
                  border: "none",
                  padding: 0,
                }}
              />
              <Bar dataKey="count" fill="#6366f1" radius={[0, 4, 4, 0]}>
                <LabelList
                  dataKey="count"
                  position="right"
                  style={{ fontSize: 11, fill: "#555" }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      )}

      {/* Salary by category - range bars (min to max) */}
      {data.salary_stats.by_category.length > 0 && (
        <ChartCard title="Average Salary Range by Category (PLN/mo)">
          <SalaryRangeChart data={data.salary_stats.by_category} />
        </ChartCard>
      )}

      {/* Seniority (pie, only when no seniority filter) + Work Type */}
      <Box
        sx={{ display: "grid", gridTemplateColumns: { md: "1fr 1fr" }, gap: 3 }}
      >
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
                  {data.by_seniority.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  content={(props) => <ChartTooltip {...(props as ComponentProps<typeof ChartTooltip>)} />}
                  contentStyle={{
                    background: "transparent",
                    border: "none",
                    padding: 0,
                  }}
                />
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
                <Tooltip
                  content={(props) => <ChartTooltip {...(props as ComponentProps<typeof ChartTooltip>)} />}
                  contentStyle={{
                    background: "transparent",
                    border: "none",
                    padding: 0,
                  }}
                />
                <Bar dataKey="count" fill="#0ea5e9" radius={[4, 4, 0, 0]}>
                  <LabelList
                    dataKey="count"
                    position="top"
                    style={{ fontSize: 11, fill: "#555" }}
                  />
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
              <Tooltip
                content={(props) => <ChartTooltip {...(props as ComponentProps<typeof ChartTooltip>)} />}
                contentStyle={{
                  background: "transparent",
                  border: "none",
                  padding: 0,
                }}
              />
              <Area
                type="monotone"
                dataKey="count"
                stroke="#6366f1"
                fill="#c4b5fd"
                fillOpacity={0.5}
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>
      )}

      {/* Top companies + Top locations */}
      <Box
        sx={{ display: "grid", gridTemplateColumns: { md: "1fr 1fr" }, gap: 3 }}
      >
        {data.top_companies.length > 0 && (
          <ChartCard title="Top Companies">
            <Box
              sx={{
                maxHeight: 320,
                overflow: "auto",
                "&::-webkit-scrollbar": { width: 8 },
                "&::-webkit-scrollbar-track": { bgcolor: "background.default" },
                "&::-webkit-scrollbar-thumb": {
                  bgcolor: "grey.600",
                  borderRadius: 1,
                },
                "&::-webkit-scrollbar-thumb:hover": { bgcolor: "grey.500" },
                scrollbarColor: (theme) =>
                  `${theme.palette.grey[600]} ${theme.palette.background.default}`,
              }}
            >
              {data.top_companies.map((c, i) => (
                <Box
                  key={c.company}
                  sx={{
                    display: "flex",
                    justifyContent: "space-between",
                    py: 0.75,
                    px: 0.5,
                    borderBottom: 1,
                    borderColor: "divider",
                  }}
                >
                  <Box sx={{ display: "flex", gap: 1, minWidth: 0 }}>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ width: 24, textAlign: "right", flexShrink: 0 }}
                    >
                      {i + 1}.
                    </Typography>
                    <Typography variant="body2" noWrap>
                      {c.company}
                    </Typography>
                  </Box>
                  <Typography
                    variant="body2"
                    fontWeight={600}
                    sx={{ flexShrink: 0, ml: 1 }}
                  >
                    {c.count}
                  </Typography>
                </Box>
              ))}
            </Box>
          </ChartCard>
        )}

        {data.top_locations.length > 0 && (
          <ChartCard title="Top Locations">
            <Box
              sx={{
                maxHeight: 320,
                overflow: "auto",
                "&::-webkit-scrollbar": { width: 8 },
                "&::-webkit-scrollbar-track": { bgcolor: "background.default" },
                "&::-webkit-scrollbar-thumb": {
                  bgcolor: "grey.600",
                  borderRadius: 1,
                },
                "&::-webkit-scrollbar-thumb:hover": { bgcolor: "grey.500" },
                scrollbarColor: (theme) =>
                  `${theme.palette.grey[600]} ${theme.palette.background.default}`,
              }}
            >
              {data.top_locations.map((l, i) => (
                <Box
                  key={l.location}
                  sx={{
                    display: "flex",
                    justifyContent: "space-between",
                    py: 0.75,
                    px: 0.5,
                    borderBottom: 1,
                    borderColor: "divider",
                  }}
                >
                  <Box sx={{ display: "flex", gap: 1, minWidth: 0 }}>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ width: 24, textAlign: "right", flexShrink: 0 }}
                    >
                      {i + 1}.
                    </Typography>
                    <Typography variant="body2" noWrap>
                      {l.location}
                    </Typography>
                  </Box>
                  <Typography
                    variant="body2"
                    fontWeight={600}
                    sx={{ flexShrink: 0, ml: 1 }}
                  >
                    {l.count}
                  </Typography>
                </Box>
              ))}
            </Box>
          </ChartCard>
        )}
      </Box>
    </Box>
  );
}

function KpiCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <Paper sx={{ p: 2.5 }}>
      <Typography variant="overline" color="text.secondary" fontSize={11}>
        {label}
      </Typography>
      <Typography
        variant="h5"
        fontWeight={700}
        sx={{ color: color ?? "text.primary", mt: 0.5 }}
      >
        {value}
      </Typography>
    </Paper>
  );
}

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Paper sx={{ p: 3 }}>
      <Typography
        variant="subtitle2"
        fontWeight={600}
        color="text.secondary"
        sx={{ mb: 2 }}
      >
        {title}
      </Typography>
      {children}
    </Paper>
  );
}
