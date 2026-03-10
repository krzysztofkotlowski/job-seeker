import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { vi } from "vitest";

import { CHART_MAX_HEIGHT, ResumeAnalysisPage } from "./ResumeAnalysisPage";
import { api } from "../api/client";

vi.mock("../api/client", () => ({
  api: {
    listCategories: vi.fn().mockResolvedValue(["Backend", "Frontend"]),
    embeddingStatus: vi.fn().mockResolvedValue({
      available: false,
      current_db_total: 0,
      run: null,
      active_run: null,
      active_index_name: null,
      active_indexed_documents: 0,
      current_config_matches_active: false,
      reindex_required: true,
      legacy_indices: [],
    }),
    resumeAnalyze: vi.fn(),
    resumeRecommendations: vi.fn().mockResolvedValue({
      status: "ok",
      recommendations: [],
    }),
    resumeSummarize: vi.fn(),
    resumeSummarizeStream: vi
      .fn()
      .mockResolvedValue({ summary: "", recommendations: [] }),
  },
}));

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

describe("ResumeAnalysisPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.useRealTimers();
    vi.mocked(api.listCategories).mockResolvedValue(["Backend", "Frontend"]);
    vi.mocked(api.embeddingStatus).mockResolvedValue({
      available: false,
      current_db_total: 0,
      run: null,
      active_run: null,
      active_index_name: null,
      active_indexed_documents: 0,
      current_config_matches_active: false,
      reindex_required: true,
      legacy_indices: [],
    });
    vi.mocked(api.resumeRecommendations).mockResolvedValue({
      status: "ok",
      recommendations: [],
    });
  });

  afterEach(() => {
    try {
      vi.runOnlyPendingTimers();
    } catch {
      // ignore when fake timers were not active
    }
    vi.useRealTimers();
  });

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
          matching_skills: [
            { skill: "Python", weight: 8 },
            { skill: "Django", weight: 5 },
          ],
          skills_to_add: [{ skill: "PostgreSQL", weight: 6 }],
        },
      ],
    });

    renderWithRouter(<ResumeAnalysisPage />);
    await waitFor(() => expect(api.listCategories).toHaveBeenCalled());

    const user = userEvent.setup();
    const file = new File(["fake pdf content"], "resume.pdf", {
      type: "application/pdf",
    });
    const input = document.getElementById("resume-upload") as HTMLInputElement;
    expect(input).toBeTruthy();
    await user.upload(input, file);

    await waitFor(() => expect(api.resumeAnalyze).toHaveBeenCalled());

    await waitFor(
      () => {
        expect(screen.getByText(/Python/)).toBeInTheDocument();
        expect(screen.getByText("Backend (75/100)")).toBeInTheDocument();
      },
      { timeout: 5000 },
    );
  }, 10000);

  it("uses CHART_MAX_HEIGHT for chart sizing", () => {
    expect(CHART_MAX_HEIGHT).toBe(1200);
  });

  it("retries recommendations automatically after indexing finishes", async () => {
    vi.mocked(api.embeddingStatus)
      .mockResolvedValueOnce({
        available: true,
        current_db_total: 100,
        run: {
          id: "run-1",
          status: "running",
          mode: "full",
          unique_only: true,
          embed_source: "ollama",
          embed_model: "nomic-embed-text",
          embed_dims: 768,
          db_total_snapshot: 100,
          selection_total: 50,
          target_total: 50,
          processed: 25,
          indexed: 25,
          failed: 0,
          index_alias: "jobseeker_jobs_active",
          physical_index_name: "jobseeker_jobs_run_1",
          celery_task_id: "celery-1",
          error_message: null,
          started_at: null,
          finished_at: null,
          updated_at: null,
          activated_at: null,
        },
        active_run: null,
        active_index_name: null,
        active_indexed_documents: 0,
        current_config_matches_active: false,
        reindex_required: true,
        legacy_indices: [],
      })
      .mockResolvedValueOnce({
        available: true,
        current_db_total: 100,
        run: {
          id: "run-1",
          status: "completed",
          mode: "full",
          unique_only: true,
          embed_source: "ollama",
          embed_model: "nomic-embed-text",
          embed_dims: 768,
          db_total_snapshot: 100,
          selection_total: 50,
          target_total: 50,
          processed: 50,
          indexed: 50,
          failed: 0,
          index_alias: "jobseeker_jobs_active",
          physical_index_name: "jobseeker_jobs_run_1",
          celery_task_id: "celery-1",
          error_message: null,
          started_at: null,
          finished_at: null,
          updated_at: null,
          activated_at: "2026-03-10T19:53:28Z",
        },
        active_run: {
          id: "run-1",
          status: "completed",
          mode: "full",
          unique_only: true,
          embed_source: "ollama",
          embed_model: "nomic-embed-text",
          embed_dims: 768,
          db_total_snapshot: 100,
          selection_total: 50,
          target_total: 50,
          processed: 50,
          indexed: 50,
          failed: 0,
          index_alias: "jobseeker_jobs_active",
          physical_index_name: "jobseeker_jobs_run_1",
          celery_task_id: "celery-1",
          error_message: null,
          started_at: null,
          finished_at: null,
          updated_at: null,
          activated_at: "2026-03-10T19:53:28Z",
        },
        active_index_name: "jobseeker_jobs_active",
        active_indexed_documents: 50,
        current_config_matches_active: true,
        reindex_required: false,
        legacy_indices: [],
      });
    vi.mocked(api.resumeAnalyze).mockResolvedValue({
      extracted_skills: ["Python", "Docker"],
      match_count: 0,
      matches: [],
      by_category: [],
    });
    vi.mocked(api.resumeRecommendations).mockResolvedValue({
      status: "ok",
      recommendations: [
        {
          job: {
            id: "job-1",
            title: "Senior Python Developer",
            company: "Acme",
            url: "https://example.com/job-1",
            category: "Backend",
          },
          score: 0.9,
        },
      ],
    });

    renderWithRouter(<ResumeAnalysisPage />);
    await waitFor(() => expect(api.listCategories).toHaveBeenCalled());

    const user = userEvent.setup();
    const file = new File(["fake pdf content"], "resume.pdf", {
      type: "application/pdf",
    });
    const input = document.getElementById("resume-upload") as HTMLInputElement;
    await user.upload(input, file);

    await waitFor(() => expect(api.resumeAnalyze).toHaveBeenCalled());
    expect(api.resumeRecommendations).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(
        screen.getByText(
          /Indexing is still running: 25 \/ 50. Recommendations will retry automatically./i,
        ),
      ).toBeInTheDocument();
    });

    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });

    await waitFor(() => expect(api.embeddingStatus).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(api.resumeRecommendations).toHaveBeenCalledTimes(1));
    expect(
      await screen.findByText(/Senior Python Developer/i),
    ).toBeInTheDocument();
  }, 10000);

  it("shows a no-active-index message when no active vector docs exist", async () => {
    vi.mocked(api.embeddingStatus).mockResolvedValue({
      available: true,
      current_db_total: 100,
      run: null,
      active_run: null,
      active_index_name: null,
      active_indexed_documents: 0,
      current_config_matches_active: false,
      reindex_required: true,
      legacy_indices: [],
    });
    vi.mocked(api.resumeAnalyze).mockResolvedValue({
      extracted_skills: ["Python"],
      match_count: 0,
      matches: [],
      by_category: [],
    });

    renderWithRouter(<ResumeAnalysisPage />);
    await waitFor(() => expect(api.listCategories).toHaveBeenCalled());

    const user = userEvent.setup();
    const file = new File(["fake pdf content"], "resume.pdf", {
      type: "application/pdf",
    });
    const input = document.getElementById("resume-upload") as HTMLInputElement;
    await user.upload(input, file);

    await waitFor(() => expect(api.resumeAnalyze).toHaveBeenCalled());
    expect(api.resumeRecommendations).not.toHaveBeenCalled();
    expect(
      await screen.findByText(/No active vector index yet. Run Re-index all./i),
    ).toBeInTheDocument();
  });

  it("shows the backend reindex message when recommendations require rebuild", async () => {
    vi.mocked(api.embeddingStatus).mockResolvedValue({
      available: true,
      current_db_total: 100,
      run: {
        id: "run-2",
        status: "completed",
        mode: "full",
        unique_only: true,
        embed_source: "ollama",
        embed_model: "nomic-embed-text",
        embed_dims: 768,
        db_total_snapshot: 100,
        selection_total: 50,
        target_total: 50,
        processed: 50,
        indexed: 50,
        failed: 0,
        index_alias: "jobseeker_jobs_active",
        physical_index_name: "jobseeker_jobs_run_2",
        celery_task_id: "celery-2",
        error_message: null,
        started_at: null,
        finished_at: null,
        updated_at: null,
        activated_at: "2026-03-10T19:53:28Z",
      },
      active_run: {
        id: "run-2",
        status: "completed",
        mode: "full",
        unique_only: true,
        embed_source: "ollama",
        embed_model: "nomic-embed-text",
        embed_dims: 768,
        db_total_snapshot: 100,
        selection_total: 50,
        target_total: 50,
        processed: 50,
        indexed: 50,
        failed: 0,
        index_alias: "jobseeker_jobs_active",
        physical_index_name: "jobseeker_jobs_run_2",
        celery_task_id: "celery-2",
        error_message: null,
        started_at: null,
        finished_at: null,
        updated_at: null,
        activated_at: "2026-03-10T19:53:28Z",
      },
      active_index_name: "jobseeker_jobs_active",
      active_indexed_documents: 50,
      current_config_matches_active: false,
      reindex_required: true,
      legacy_indices: [],
    });
    vi.mocked(api.resumeAnalyze).mockResolvedValue({
      extracted_skills: ["Python"],
      match_count: 0,
      matches: [],
      by_category: [],
    });
    vi.mocked(api.resumeRecommendations).mockResolvedValue({
      status: "reindex_required",
      message: "The active recommendation index uses a different embedding shape. Run a full rebuild.",
      recommendations: [],
      active_run: null,
      config_matches_active: false,
    });

    renderWithRouter(<ResumeAnalysisPage />);
    await waitFor(() => expect(api.listCategories).toHaveBeenCalled());

    const user = userEvent.setup();
    const file = new File(["fake pdf content"], "resume.pdf", {
      type: "application/pdf",
    });
    const input = document.getElementById("resume-upload") as HTMLInputElement;
    await user.upload(input, file);

    await waitFor(() => expect(api.resumeRecommendations).toHaveBeenCalled());
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /The active recommendation index uses a different embedding shape. Run a full rebuild./i,
    );
  });

  it("does not show RAG indexing guidance when the resume produced no extracted skills", async () => {
    vi.mocked(api.resumeAnalyze).mockResolvedValue({
      extracted_skills: [],
      match_count: 0,
      matches: [],
      by_category: [],
      message: "No skills from the PDF matched our system (skills from scraped offers).",
    });

    renderWithRouter(<ResumeAnalysisPage />);
    await waitFor(() => expect(api.listCategories).toHaveBeenCalled());

    const user = userEvent.setup();
    const file = new File(["fake pdf content"], "resume.pdf", {
      type: "application/pdf",
    });
    const input = document.getElementById("resume-upload") as HTMLInputElement;
    await user.upload(input, file);

    await waitFor(() => expect(api.resumeAnalyze).toHaveBeenCalled());
    expect(api.resumeRecommendations).not.toHaveBeenCalled();
    expect(
      await screen.findByText(/No skills from the PDF matched our system/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Index jobs for RAG recommendations/i),
    ).not.toBeInTheDocument();
  });
});
