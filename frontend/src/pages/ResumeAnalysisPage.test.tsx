import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { vi } from "vitest";

import { CHART_MAX_HEIGHT, ResumeAnalysisPage } from "./ResumeAnalysisPage";
import { api } from "../api/client";

vi.mock("../api/client", () => ({
  api: {
    listCategories: vi.fn().mockResolvedValue(["Backend", "Frontend"]),
    resumeAnalyze: vi.fn(),
    resumeSummarize: vi.fn(),
  },
}));

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

describe("ResumeAnalysisPage", () => {
  it("shows upload area and fetches categories", async () => {
    renderWithRouter(<ResumeAnalysisPage />);

    await waitFor(() => {
      expect(api.listCategories).toHaveBeenCalled();
    });

    expect(screen.getByText(/Resume analysis/i)).toBeInTheDocument();
    expect(screen.getByText(/Choose PDF/i)).toBeInTheDocument();
  });

  it("shows skills and bar charts after successful upload", async () => {
    vi.mocked(api.resumeAnalyze).mockResolvedValue({
      extracted_skills: ["Python", "Django"],
      match_count: 2,
      matches: [],
      by_category: [
        {
          category: "Backend",
          job_count: 10,
          match_score: 75,
          matching_skills: [{ skill: "Python", weight: 8 }, { skill: "Django", weight: 5 }],
          skills_to_add: [{ skill: "PostgreSQL", weight: 6 }],
        },
      ],
    });

    renderWithRouter(<ResumeAnalysisPage />);
    await waitFor(() => expect(api.listCategories).toHaveBeenCalled());

    const user = userEvent.setup();
    const file = new File(["fake pdf content"], "resume.pdf", { type: "application/pdf" });
    const input = document.getElementById("resume-upload") as HTMLInputElement;
    expect(input).toBeTruthy();
    await user.upload(input, file);

    await waitFor(() => expect(api.resumeAnalyze).toHaveBeenCalled());

    expect(await screen.findByText(/Python/)).toBeInTheDocument();
    expect(await screen.findByText("Backend (75/100)")).toBeInTheDocument();
  });

  it("uses CHART_MAX_HEIGHT for chart sizing", () => {
    expect(CHART_MAX_HEIGHT).toBe(1200);
  });
});
