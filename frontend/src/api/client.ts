import type {
  Job,
  PaginatedResponse,
  ParsedJob,
  DuplicateCheck,
  SkillsSummary,
  JobStatus,
  ImportStatus,
  DetectedSkill,
  AnalyticsData,
  ResumeAnalyzeResult,
} from "./types";
import { getTokenForRequest } from "../auth/tokenProvider";

const BASE = "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getTokenForRequest();
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err =
      body?.error?.message ||
      body?.detail?.message ||
      body?.detail ||
      `HTTP ${res.status}`;
    throw new Error(err);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  parseUrl: (url: string) =>
    request<ParsedJob>("/jobs/parse", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  createJob: (job: ParsedJob) =>
    request<Job>("/jobs", {
      method: "POST",
      body: JSON.stringify(job),
    }),

  listJobs: (params?: {
    page?: number;
    per_page?: number;
    status?: string;
    source?: string;
    category?: string;
    seniority?: string;
    skill?: string;
    skills?: string;
    search?: string;
    is_reposted?: boolean;
    work_type?: string;
    location?: string;
    sort_by?: string;
    group_duplicates?: boolean;
    saved?: boolean;
  }) => {
    const sp = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
      });
    }
    const qs = sp.toString();
    return request<PaginatedResponse<Job>>(`/jobs${qs ? `?${qs}` : ""}`);
  },

  listCategories: () => request<string[]>("/jobs/categories"),

  listWorkTypes: () => request<string[]>("/jobs/work-types"),

  listLocations: () => request<string[]>("/jobs/locations"),

  listSeniorities: () => request<string[]>("/jobs/seniorities"),

  listTopSkills: (top = 50) => request<string[]>(`/jobs/top-skills?top=${top}`),

  getJob: (id: string) => request<Job>(`/jobs/${id}`),

  updateJob: (
    id: string,
    update: { status?: JobStatus; notes?: string; applied_date?: string; is_reposted?: boolean; saved?: boolean },
  ) =>
    request<Job>(`/jobs/${id}`, {
      method: "PATCH",
      body: JSON.stringify(update),
    }),

  deleteJob: (id: string) =>
    request<void>(`/jobs/${id}`, { method: "DELETE" }),

  findByUrl: (url: string) =>
    request<{ id: string }>(`/jobs/find-by-url?url=${encodeURIComponent(url)}`),

  checkDuplicate: (url: string) =>
    request<DuplicateCheck>(`/jobs/check-duplicate?url=${encodeURIComponent(url)}`),

  skillsSummary: (params?: { top?: number; category?: string; page?: number; per_page?: number; search?: string }) => {
    const sp = new URLSearchParams();
    if (params) {
      if (params.top) sp.set("top", String(params.top));
      if (params.category) sp.set("category", params.category);
      if (params.page) sp.set("page", String(params.page));
      if (params.per_page) sp.set("per_page", String(params.per_page));
      if (params.search) sp.set("search", params.search);
    }
    return request<SkillsSummary>(`/skills/summary?${sp.toString()}`);
  },

  importStatus: () => request<ImportStatus>("/import/status"),

  importStart: () =>
    request<{ message: string; running: boolean }>("/import/start", {
      method: "POST",
    }),

  importStartSource: (source: string) =>
    request<{ message: string; running: boolean }>(`/import/start/${source}`, {
      method: "POST",
    }),

  importCancel: () =>
    request<{ message: string }>("/import/cancel", {
      method: "POST",
    }),

  recalculateSalaries: () =>
    request<{ updated: number }>("/jobs/recalculate-salaries", {
      method: "POST",
    }),

  fixCategories: () =>
    request<{ fixed: number }>("/jobs/fix-categories", {
      method: "POST",
    }),

  detectedSkills: (jobId: string) =>
    request<DetectedSkill[]>(`/skills/detected?job_id=${encodeURIComponent(jobId)}`),

  analytics: (params?: {
    seniority?: string;
    source?: string;
    category?: string;
    skill?: string;
    skills?: string;
    search?: string;
    is_reposted?: boolean;
    work_type?: string;
    location?: string;
    saved?: boolean;
    group_duplicates?: boolean;
  }) => {
    const sp = new URLSearchParams();
    if (params?.seniority) sp.set("seniority", params.seniority);
    if (params?.source) sp.set("source", params.source);
    if (params?.category) sp.set("category", params.category);
    if (params?.skill) sp.set("skill", params.skill);
    if (params?.skills) sp.set("skills", params.skills);
    if (params?.search) sp.set("search", params.search);
    if (params?.is_reposted !== undefined) sp.set("is_reposted", String(params.is_reposted));
    if (params?.work_type) sp.set("work_type", params.work_type);
    if (params?.location) sp.set("location", params.location);
    if (params?.saved !== undefined) sp.set("saved", String(params.saved));
    if (params?.group_duplicates !== undefined) sp.set("group_duplicates", String(params.group_duplicates));
    const qs = sp.toString();
    return request<AnalyticsData>(`/jobs/analytics${qs ? `?${qs}` : ""}`);
  },

  /** Trigger DB backup; returns blob for download. */
  createBackup: async (): Promise<Blob> => {
    const token = await getTokenForRequest();
    const headers = new Headers();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const res = await fetch(`${BASE}/backup/create`, { method: "POST", headers });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Backup failed: ${res.status}`);
    }
    return res.blob();
  },

  /** Upload resume (PDF or JSON), extract keywords, return job matches. */
  resumeAnalyze: async (file: File, signal?: AbortSignal): Promise<ResumeAnalyzeResult> => {
    const token = await getTokenForRequest();
    const form = new FormData();
    form.append("file", file);
    const headers = new Headers();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const res = await fetch(`${BASE}/resume/analyze`, {
      method: "POST",
      body: form,
      headers,
      signal,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const msg = body?.detail || body?.error?.message || `Resume analyze failed: ${res.status}`;
      throw new Error(Array.isArray(msg) ? msg[0]?.msg || String(msg) : msg);
    }
    return res.json();
  },

  /** Generate AI summary for resume analysis. Call after analyze. */
  resumeSummarize: async (
    data: { extracted_skills: string[]; matches: unknown[]; by_category: unknown[] },
    signal?: AbortSignal,
  ): Promise<{ summary: string }> => {
    const token = await getTokenForRequest();
    const headers = new Headers();
    headers.set("Content-Type", "application/json");
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const res = await fetch(`${BASE}/resume/summarize`, {
      method: "POST",
      body: JSON.stringify(data),
      headers,
      signal,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const msg = body?.detail || body?.error?.message || `Summary failed: ${res.status}`;
      throw new Error(typeof msg === "string" ? msg : Array.isArray(msg) ? msg[0]?.msg || String(msg) : String(msg));
    }
    return res.json();
  },
};
