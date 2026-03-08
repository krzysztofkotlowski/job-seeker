import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { vi } from "vitest";

import { DashboardPage } from "./DashboardPage";
import { api } from "../api/client";
import { ToastProvider } from "../contexts/ToastContext";

vi.mock("../api/client", () => ({
  api: {
    analytics: vi.fn().mockResolvedValue({
      total_jobs: 5,
      by_status: { new: 3, applied: 2 },
      saved_count: 0,
      by_source: {},
      by_category: [{ category: "Backend", count: 3 }],
      by_seniority: [],
      by_work_type: [],
      salary_stats: {
        avg_min_pln: 12000,
        avg_max_pln: 18000,
        by_category: [
          { category: "Backend", avg_min: 15000, avg_max: 22000 },
          { category: "Frontend", avg_min: 12000, avg_max: 18000 },
        ],
      },
      added_over_time: [],
      top_companies: [],
      top_locations: [],
      reposted_count: 0,
    }),
    listSeniorities: vi.fn().mockResolvedValue(["Junior", "Mid", "Senior"]),
  },
}));

function renderWithRouter(ui: React.ReactElement) {
  return render(
    <BrowserRouter>
      <ToastProvider>{ui}</ToastProvider>
    </BrowserRouter>,
  );
}

describe("DashboardPage", () => {
  it("renders analytics and charts", async () => {
    renderWithRouter(<DashboardPage />);

    await waitFor(() => expect(api.analytics).toHaveBeenCalled());

    expect(await screen.findByText(/5/)).toBeInTheDocument();
  });

  it("renders salary range chart when by_category has data", async () => {
    renderWithRouter(<DashboardPage />);

    await waitFor(() => expect(api.analytics).toHaveBeenCalled());

    expect(
      await screen.findByText("Average Salary Range by Category (PLN/mo)"),
    ).toBeInTheDocument();
  });

  it("shows avg salary from salary_stats when by_category has ranges", async () => {
    renderWithRouter(<DashboardPage />);

    await waitFor(() => expect(api.analytics).toHaveBeenCalled());

    expect(screen.getByText("12 000 - 18 000")).toBeInTheDocument();
  });
});
