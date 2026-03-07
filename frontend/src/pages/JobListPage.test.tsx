import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { vi } from "vitest";

import { JobListPage } from "./JobListPage";
import { api } from "../api/client";
import type { Job } from "../api/types";
import { ToastProvider } from "../contexts/ToastContext";

vi.mock("../api/client", () => ({
  api: {
    listJobs: vi.fn().mockResolvedValue({
      items: [
        {
          id: "1",
          url: "https://example.com/1",
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
          duplicate_count: 1,
        },
      ],
      total: 1,
      page: 1,
      per_page: 50,
      pages: 1,
    }),
    analytics: vi.fn().mockResolvedValue({
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
    }),
    listWorkTypes: vi.fn().mockResolvedValue([]),
    listLocations: vi.fn().mockResolvedValue([]),
    listCategories: vi.fn().mockResolvedValue([]),
    listSeniorities: vi.fn().mockResolvedValue([]),
    listTopSkills: vi.fn().mockResolvedValue([]),
  },
}));

const defaultJob: Job = {
  id: "1",
  url: "https://example.com/1",
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
  duplicate_count: 1,
};

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
}

function renderWithRouter(ui: React.ReactElement) {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>{ui}</ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>,
  );
}

describe("JobListPage", () => {
  beforeEach(() => {
    vi.mocked(api.listJobs).mockClear();
    vi.mocked(api.analytics).mockClear();
    localStorage.clear();
  });

  it("renders jobs and shows status counts", async () => {
    renderWithRouter(<JobListPage />);

    await waitFor(() => {
      expect(api.listJobs).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText("Backend Engineer")).toBeInTheDocument();

    // The status chips should reflect analytics totals.
    expect(await screen.findByText(/All \(1\)/)).toBeInTheDocument();
    expect(await screen.findByText(/New \(1\)/)).toBeInTheDocument();
  });

  it("passes same group_duplicates to listJobs and analytics", async () => {
    renderWithRouter(<JobListPage />);

    await waitFor(() => expect(api.listJobs).toHaveBeenCalled());
    await waitFor(() => expect(api.analytics).toHaveBeenCalled());

    expect(api.listJobs).toHaveBeenCalledWith(
      expect.objectContaining({ group_duplicates: true }),
    );
    expect(api.analytics).toHaveBeenCalledWith(
      expect.objectContaining({ group_duplicates: true }),
    );
  });

  it("shows consistent job count and status chip totals", async () => {
    vi.mocked(api.listJobs).mockResolvedValue({
      items: [defaultJob],
      total: 10,
      page: 1,
      per_page: 50,
      pages: 1,
    });
    vi.mocked(api.analytics).mockResolvedValue({
      total_jobs: 10,
      by_status: { new: 6, seen: 4 },
      saved_count: 2,
      by_source: {},
      by_category: [],
      by_seniority: [],
      by_work_type: [],
      salary_stats: { avg_min_pln: null, avg_max_pln: null, by_category: [] },
      added_over_time: [],
      top_companies: [],
      top_locations: [],
      reposted_count: 0,
    });

    renderWithRouter(<JobListPage />);

    await waitFor(
      () => {
        expect(screen.getByText((_, el) => el?.textContent === "10 jobs found")).toBeInTheDocument();
      },
      { timeout: 3000 },
    );
    expect(screen.getByText(/All \(10\)/)).toBeInTheDocument();
    expect(screen.getByText(/New \(6\)/)).toBeInTheDocument();
    expect(screen.getByText(/Seen \(4\)/)).toBeInTheDocument();
    expect(screen.getByText(/Saved \(2\)/)).toBeInTheDocument();
  });
});
