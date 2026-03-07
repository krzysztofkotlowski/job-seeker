import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { vi } from "vitest";

import { SkillsPage } from "./SkillsPage";
import { api } from "../api/client";
import { ToastProvider } from "../contexts/ToastContext";

vi.mock("../api/client", () => ({
  api: {
    skillsSummary: vi.fn().mockResolvedValue({
      total_jobs: 10,
      total_skills: 25,
      page: 1,
      per_page: 50,
      pages: 1,
      top_skills: [
        { skill: "Python", count: 8, required_count: 6 },
        { skill: "JavaScript", count: 6, required_count: 4 },
      ],
      required_skills: [{ skill: "Python", count: 6 }],
      nice_to_have_skills: [{ skill: "Docker", count: 4 }],
    }),
    listCategories: vi.fn().mockResolvedValue(["Backend", "Frontend"]),
  },
}));

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <BrowserRouter>
      <ToastProvider>{ui}</ToastProvider>
    </BrowserRouter>,
  );
}

describe("SkillsPage", () => {
  it("renders skills summary and category filter", async () => {
    renderWithProviders(<SkillsPage />);

    await waitFor(() => expect(api.skillsSummary).toHaveBeenCalled());
    await waitFor(() => expect(api.listCategories).toHaveBeenCalled());

    expect(await screen.findByText(/Skills Overview/)).toBeInTheDocument();
    expect(
      await screen.findByText(/25 skills across 10 jobs/),
    ).toBeInTheDocument();
    expect(await screen.findByText(/Python/)).toBeInTheDocument();
    expect(await screen.findByText(/JavaScript/)).toBeInTheDocument();
  });

  it("shows empty state when no data", async () => {
    vi.mocked(api.skillsSummary).mockResolvedValueOnce({
      total_jobs: 0,
      total_skills: 0,
      page: 1,
      per_page: 50,
      pages: 1,
      top_skills: [],
      required_skills: [],
      nice_to_have_skills: [],
    });

    renderWithProviders(<SkillsPage />);

    await waitFor(() => expect(api.skillsSummary).toHaveBeenCalled());

    expect(await screen.findByText(/No skills data yet/)).toBeInTheDocument();
  });
});
