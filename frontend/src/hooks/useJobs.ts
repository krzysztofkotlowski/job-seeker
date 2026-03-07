import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Job, PaginatedResponse } from "../api/types";
import type { AnalyticsData } from "../api/types";

export const jobsKeys = {
  all: ["jobs"] as const,
  list: (params: Record<string, unknown>) =>
    ["jobs", "list", params] as const,
  analytics: (params: Record<string, unknown>) =>
    ["jobs", "analytics", params] as const,
  filters: () => ["jobs", "filters"] as const,
};

export function useJobsList(params: {
  page: number;
  perPage: number;
  status?: string;
  source?: string;
  category?: string;
  seniority?: string;
  skills?: string;
  search?: string;
  isReposted?: boolean;
  workType?: string;
  location?: string;
  sortBy?: string;
  groupDuplicates?: boolean;
  saved?: boolean;
  enabled?: boolean;
}) {
  const {
    page,
    perPage,
    status,
    source,
    category,
    seniority,
    skills,
    search,
    isReposted,
    workType,
    location,
    sortBy,
    groupDuplicates,
    saved,
    enabled = true,
  } = params;

  return useQuery({
    queryKey: jobsKeys.list({
      page,
      perPage,
      status,
      source,
      category,
      seniority,
      skills,
      search,
      isReposted,
      workType,
      location,
      sortBy,
      groupDuplicates,
      saved,
    }),
    queryFn: () =>
      api.listJobs({
        page,
        per_page: perPage,
        status: status || undefined,
        source: source || undefined,
        category: category || undefined,
        seniority: seniority || undefined,
        skills: skills || undefined,
        search: search || undefined,
        is_reposted: isReposted,
        work_type: workType || undefined,
        location: location || undefined,
        sort_by: sortBy || undefined,
        group_duplicates: groupDuplicates,
        saved: saved,
      }) as Promise<PaginatedResponse<Job>>,
    enabled,
    staleTime: 30_000,
    retry: 2,
  });
}

export function useJobsAnalytics(params: {
  seniority?: string;
  source?: string;
  category?: string;
  skills?: string;
  search?: string;
  isReposted?: boolean;
  workType?: string;
  location?: string;
  saved?: boolean;
  groupDuplicates?: boolean;
  enabled?: boolean;
}) {
  const {
    seniority,
    source,
    category,
    skills,
    search,
    isReposted,
    workType,
    location,
    saved,
    groupDuplicates,
    enabled = true,
  } = params;

  return useQuery({
    queryKey: jobsKeys.analytics({
      seniority,
      source,
      category,
      skills,
      search,
      isReposted,
      workType,
      location,
      saved,
      groupDuplicates,
    }),
    queryFn: () =>
      api.analytics({
        seniority: seniority || undefined,
        source: source || undefined,
        category: category || undefined,
        skills: skills || undefined,
        search: search || undefined,
        is_reposted: isReposted,
        work_type: workType || undefined,
        location: location || undefined,
        saved: saved,
        group_duplicates: groupDuplicates,
      }) as Promise<AnalyticsData>,
    enabled,
    staleTime: 30_000,
    retry: 2,
  });
}

export function useJobsFilters() {
  return useQuery({
    queryKey: jobsKeys.filters(),
    queryFn: async () => {
      const [workTypes, locations, categories, seniorities, topSkills] =
        await Promise.all([
          api.listWorkTypes(),
          api.listLocations(),
          api.listCategories(),
          api.listSeniorities(),
          api.listTopSkills(100),
        ]);
      return {
        workTypes,
        locations,
        categories,
        seniorities,
        topSkills,
      };
    },
    staleTime: 5 * 60 * 1000,
    retry: 2,
  });
}
