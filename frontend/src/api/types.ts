export interface Salary {
  min: number | null;
  max: number | null;
  currency: string | null;
  type: string | null;
  period: string | null;
  min_pln: number | null;
  max_pln: number | null;
}

export interface DetectedSkill {
  skill_name: string;
  source_field: string;
}

export type JobStatus = "new" | "seen" | "applied" | "interview" | "offer" | "rejected";

export interface AlternateListing {
  id: string;
  source: string;
  url: string;
}

export interface Job {
  id: string;
  url: string;
  source: string;
  title: string;
  company: string;
  location: string[];
  salary: Salary | null;
  skills_required: string[];
  skills_nice_to_have: string[];
  seniority: string | null;
  work_type: string | null;
  employment_types: string[];
  description: string | null;
  category: string | null;
  is_reposted: boolean;
  original_job_id: string | null;
  date_published: string | null;
  date_expires: string | null;
  date_added: string;
  status: JobStatus;
  applied_date: string | null;
  notes: string;
  duplicate_count?: number;
  detected_skills?: string[];
  saved?: boolean;
  alternate_listings?: AlternateListing[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface ParsedJob {
  url: string;
  source: string;
  title: string;
  company: string;
  location: string[];
  salary: Salary | null;
  skills_required: string[];
  skills_nice_to_have: string[];
  seniority: string | null;
  work_type: string | null;
  employment_types: string[];
  description: string | null;
  category: string | null;
  date_published: string | null;
  date_expires: string | null;
}

export interface DuplicateCheck {
  is_duplicate: boolean;
  existing_job: Job | null;
}

export interface SkillStat {
  skill: string;
  count: number;
  required_count?: number;
}

export interface SkillsSummary {
  total_jobs: number;
  total_skills: number;
  page: number;
  per_page: number;
  pages: number;
  top_skills: SkillStat[];
  required_skills: SkillStat[];
  nice_to_have_skills: SkillStat[];
}

export type ImportTaskStatus =
  | "idle"
  | "collecting"
  | "running"
  | "done"
  | "error"
  | "cancelled";

export interface ImportTask {
  source: string;
  status: ImportTaskStatus;
  total: number;
  processed: number;
  imported: number;
  skipped: number;
  errors: number;
  error_log: string[];
  pending: number;
  started_at?: string;
  updated_at?: string;
}

export interface ImportStatus {
  running: boolean;
  tasks: ImportTask[];
}

export interface SalaryCategoryStat {
  category: string;
  avg_min: number | null;
  avg_max: number | null;
}

export interface AnalyticsData {
  total_jobs: number;
  by_status: Record<string, number>;
  by_source: Record<string, number>;
  by_category: { category: string; count: number }[];
  by_seniority: { seniority: string; count: number }[];
  by_work_type: { work_type: string; count: number }[];
  salary_stats: {
    avg_min_pln: number | null;
    avg_max_pln: number | null;
    by_category: SalaryCategoryStat[];
  };
  added_over_time: { date: string; count: number }[];
  top_companies: { company: string; count: number }[];
  top_locations: { location: string; count: number }[];
  reposted_count: number;
  saved_count: number;
}

export interface ResumeMatchItem {
  job: Job;
  matched_skills: string[];
  match_count: number;
  match_ratio: number;
}

export interface SkillWithWeight {
  skill: string;
  weight: number;
}

export interface ResumeByCategory {
  category: string;
  job_count: number;
  match_score: number;
  matching_skills: SkillWithWeight[];
  skills_to_add: SkillWithWeight[];
}

export interface ResumeRecommendation {
  job: Pick<Job, "id" | "title" | "company" | "url" | "category">;
  score?: number;
}

export interface ResumeAnalyzeResult {
  extracted_skills: string[];
  match_count: number;
  matches: ResumeMatchItem[];
  by_category: ResumeByCategory[];
  message?: string;
  summary?: string;
  recommendations?: ResumeRecommendation[];
}
