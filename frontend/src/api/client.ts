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
} from "./types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail?.message || body.detail || `HTTP ${res.status}`);
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
    const res = await fetch(`${BASE}/backup/create`, { method: "POST" });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Backup failed: ${res.status}`);
    }
    return res.blob();
  },
};
