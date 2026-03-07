import type {
  Job,
  PaginatedResponse,
  AnalyticsData,
  ImportStatus,
} from "../api/types";

export function createMockJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "1",
    url: "https://example.com/job/1",
    source: "justjoin.it",
    title: "Backend Engineer",
    company: "Acme",
    location: ["Remote"],
    salary: null,
    skills_required: [],
    skills_nice_to_have: [],
    seniority: "Mid",
    work_type: "Remote",
    employment_types: [],
    description: null,
    category: null,
    is_reposted: false,
    original_job_id: null,
    date_published: null,
    date_expires: null,
    date_added: "2024-01-01",
    status: "new",
    applied_date: null,
    notes: "",
    saved: false,
    ...overrides,
  };
}

export function createMockPaginatedJobs(
  jobs: Partial<Job>[] = [],
): PaginatedResponse<Job> {
  const items = jobs.length
    ? jobs.map((j) => createMockJob(j))
    : [createMockJob()];
  return {
    items,
    total: items.length,
    page: 1,
    per_page: 50,
    pages: 1,
  };
}

export function createMockAnalytics(
  overrides: Partial<AnalyticsData> = {},
): AnalyticsData {
  return {
    total_jobs: 1,
    by_status: { new: 1 },
    saved_count: 0,
    by_source: {},
    by_category: [],
    by_seniority: [],
    by_work_type: [],
    salary_stats: { avg_min_pln: null, avg_max_pln: null, by_category: [] },
    added_over_time: [],
    top_companies: [],
    top_locations: [],
    reposted_count: 0,
    ...overrides,
  };
}

export function createMockImportStatus(
  overrides: Partial<ImportStatus> = {},
): ImportStatus {
  return {
    running: false,
    tasks: [
      {
        source: "justjoin.it",
        status: "done",
        total: 10,
        processed: 10,
        imported: 8,
        skipped: 2,
        errors: 0,
        error_log: [],
        pending: 0,
        started_at: undefined,
        updated_at: undefined,
      },
    ],
    ...overrides,
  };
}
