import type { Job, JobStatus, ParsedJob } from "../api/types";

const fmtNum = (n: number | null) =>
  n != null ? n.toLocaleString("pl-PL", { maximumFractionDigits: 0 }) : "?";

/** Format salary for Job list/detail (with PLN conversion). */
export function formatSalary(j: Job): { plnLine: string; hourlyLine: string | null; originalLine: string | null } {
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

/** Format salary for Job detail (same as formatSalary but "Not specified" for empty). */
export function formatSalaryLines(job: Job): { plnLine: string; hourlyLine: string | null; originalLine: string | null } {
  const result = formatSalary(job);
  if (result.plnLine === "\u2014") return { ...result, plnLine: "Not specified" };
  return result;
}

/** Format salary for ParsedJob (simple min-max display). */
export function formatParsedSalary(s: ParsedJob["salary"]): string {
  if (!s || (!s.min && !s.max)) return "Not specified";
  const min = s.min?.toLocaleString() ?? "?";
  const max = s.max?.toLocaleString() ?? "?";
  return `${min} - ${max} ${s.currency ?? ""} ${s.type ? `(${s.type})` : ""}`.trim();
}

/** Status config for badges, tabs, and charts. */
export const STATUS_CONFIG: Record<
  JobStatus,
  { label: string; color: "primary" | "warning" | "success" | "error" | "info" | "default" }
> = {
  new: { label: "New", color: "primary" },
  seen: { label: "Seen", color: "default" },
  applied: { label: "Applied", color: "warning" },
  interview: { label: "Interview", color: "info" },
  offer: { label: "Offer", color: "success" },
  rejected: { label: "Rejected", color: "error" },
};

/** Hex colors for status tabs/charts (when MUI color not used). */
export const STATUS_TAB_COLORS: Record<string, string> = {
  new: "#6366f1",
  seen: "#9ca3af",
  applied: "#0ea5e9",
  interview: "#f59e0b",
  offer: "#22c55e",
  rejected: "#ef4444",
};
