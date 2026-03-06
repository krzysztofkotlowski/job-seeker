import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import App from "./App";

vi.mock("./api/client", () => ({
  api: {
    listJobs: vi.fn().mockResolvedValue({
      items: [{ id: "1", url: "https://example.com/1", source: "justjoin.it", title: "Job", company: "Co", location: [], salary: null, skills_required: [], skills_nice_to_have: [], seniority: null, work_type: null, employment_types: [], description: null, category: null, is_reposted: false, original_job_id: null, date_published: null, date_expires: null, date_added: "2024-01-01", status: "new", applied_date: null, notes: "", saved: false }],
      total: 1,
      page: 1,
      per_page: 50,
      pages: 1,
    }),
    analytics: vi.fn().mockResolvedValue({ total_jobs: 0, by_status: {}, saved_count: 0, by_source: {}, by_category: [], by_seniority: [], by_work_type: [], salary_stats: { avg_min_pln: null, avg_max_pln: null, by_category: [] }, added_over_time: [], top_companies: [], top_locations: [], reposted_count: 0 }),
    listWorkTypes: vi.fn().mockResolvedValue([]),
    listLocations: vi.fn().mockResolvedValue([]),
    listCategories: vi.fn().mockResolvedValue([]),
    listSeniorities: vi.fn().mockResolvedValue([]),
    listTopSkills: vi.fn().mockResolvedValue([]),
  },
}));

describe("App", () => {
  it("renders app with navigation", () => {
    render(<App />);
    expect(screen.getByText("Job Seeker")).toBeInTheDocument();
    expect(screen.getByText("Jobs")).toBeInTheDocument();
  });
});

