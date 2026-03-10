import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { ImportContent } from "./ImportContent";
import { api } from "../api/client";

vi.mock("../api/client", () => ({
  api: {
    importStatus: vi.fn().mockResolvedValue({
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
    }),
    importStart: vi
      .fn()
      .mockResolvedValue({ message: "Import started", running: true }),
    importStartSource: vi
      .fn()
      .mockResolvedValue({ message: "Import started", running: true }),
    importCancel: vi.fn().mockResolvedValue({ message: "Cancel requested" }),
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
    syncEmbeddings: vi.fn().mockResolvedValue({
      id: "run-1",
      status: "queued",
      mode: "full",
      unique_only: false,
      embed_source: "ollama",
      embed_model: "all-minilm",
      embed_dims: 384,
      db_total_snapshot: 10,
      selection_total: 10,
      target_total: 10,
      processed: 0,
      indexed: 0,
      failed: 0,
      index_alias: "jobseeker_jobs_active",
      physical_index_name: "jobseeker_jobs_run_1",
      celery_task_id: "celery-1",
      error_message: null,
      started_at: undefined,
      finished_at: undefined,
      updated_at: null,
      activated_at: null,
    }),
  },
}));

describe("ImportContent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.importStatus).mockResolvedValue({
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
    });
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
    vi.mocked(api.syncEmbeddings).mockResolvedValue({
      id: "run-1",
      status: "queued",
      mode: "full",
      unique_only: false,
      embed_source: "ollama",
      embed_model: "all-minilm",
      embed_dims: 384,
      db_total_snapshot: 10,
      selection_total: 10,
      target_total: 10,
      processed: 0,
      indexed: 0,
      failed: 0,
      index_alias: "jobseeker_jobs_active",
      physical_index_name: "jobseeker_jobs_run_1",
      celery_task_id: "celery-1",
      error_message: null,
      started_at: null,
      finished_at: null,
      updated_at: null,
      activated_at: null,
    });
  });

  it("shows import task status", async () => {
    render(<ImportContent />);

    await waitFor(() => {
      expect(api.importStatus).toHaveBeenCalled();
    });

    expect(await screen.findByText(/Completed/i)).toBeInTheDocument();
  });

  it("shows embedding section", async () => {
    render(<ImportContent />);

    await waitFor(() => {
      expect(api.embeddingStatus).toHaveBeenCalled();
    });

    expect(
      await screen.findByText(/Vector Index \(RAG\)/i),
    ).toBeInTheDocument();
  });

  it("shows persistent run progress and active index counts", async () => {
    vi.mocked(api.embeddingStatus).mockResolvedValue({
      available: true,
      current_db_total: 33931,
      run: {
        id: "run-1",
        status: "running",
        mode: "full",
        unique_only: false,
        embed_source: "ollama",
        embed_model: "all-minilm",
        embed_dims: 384,
        db_total_snapshot: 33931,
        selection_total: 33931,
        target_total: 33931,
        processed: 288,
        indexed: 288,
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
      active_run: {
        id: "run-0",
        status: "completed",
        mode: "full",
        unique_only: false,
        embed_source: "ollama",
        embed_model: "all-minilm",
        embed_dims: 384,
        db_total_snapshot: 12000,
        selection_total: 12000,
        target_total: 12000,
        processed: 12000,
        indexed: 12000,
        failed: 0,
        index_alias: "jobseeker_jobs_active",
        physical_index_name: "jobseeker_jobs_run_0",
        celery_task_id: "celery-0",
        error_message: null,
        started_at: null,
        finished_at: null,
        updated_at: null,
        activated_at: "2026-03-10T10:00:00Z",
      },
      active_index_name: "jobseeker_jobs_active",
      active_indexed_documents: 3000,
      current_config_matches_active: true,
      reindex_required: false,
      legacy_indices: [],
    });

    render(<ImportContent />);

    expect(await screen.findByText(/DB jobs:\s*33,931/i)).toBeInTheDocument();
    expect(
      await screen.findByText(/Selected scope:\s*33,931 \(with duplicates\)/i),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/Current run:\s*288 \/ 33,931 \(running\)/i),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/Active vector index:\s*3,000 docs/i),
    ).toBeInTheDocument();
  });

  it("restores duplicate choice from server status without auto-starting sync", async () => {
    vi.mocked(api.embeddingStatus).mockResolvedValue({
      available: true,
      current_db_total: 2,
      run: {
        id: "run-2",
        status: "completed",
        mode: "full",
        unique_only: true,
        embed_source: "ollama",
        embed_model: "all-minilm",
        embed_dims: 384,
        db_total_snapshot: 2,
        selection_total: 1,
        target_total: 1,
        processed: 1,
        indexed: 1,
        failed: 0,
        index_alias: "jobseeker_jobs_active",
        physical_index_name: "jobseeker_jobs_run_2",
        celery_task_id: "celery-2",
        error_message: null,
        started_at: null,
        finished_at: null,
        updated_at: null,
        activated_at: "2026-03-10T10:00:00Z",
      },
      active_run: null,
      active_index_name: "jobseeker_jobs_active",
      active_indexed_documents: 1,
      current_config_matches_active: true,
      reindex_required: false,
      legacy_indices: [],
    });

    render(<ImportContent />);

    await waitFor(() => {
      expect(api.embeddingStatus).toHaveBeenCalled();
    });

    expect(screen.getByRole("checkbox")).toBeChecked();
    expect(api.syncEmbeddings).not.toHaveBeenCalled();
  });

  it("disables incremental sync when a full rebuild is required", async () => {
    vi.mocked(api.embeddingStatus).mockResolvedValue({
      available: true,
      current_db_total: 10,
      run: null,
      active_run: {
        id: "run-3",
        status: "completed",
        mode: "full",
        unique_only: false,
        embed_source: "ollama",
        embed_model: "all-minilm",
        embed_dims: 384,
        db_total_snapshot: 10,
        selection_total: 10,
        target_total: 10,
        processed: 10,
        indexed: 10,
        failed: 0,
        index_alias: "jobseeker_jobs_active",
        physical_index_name: "jobseeker_jobs_run_3",
        celery_task_id: "celery-3",
        error_message: null,
        started_at: null,
        finished_at: null,
        updated_at: null,
        activated_at: "2026-03-10T10:00:00Z",
      },
      active_index_name: "jobseeker_jobs_active",
      active_indexed_documents: 10,
      current_config_matches_active: false,
      reindex_required: true,
      legacy_indices: [],
    });

    render(<ImportContent />);

    expect(
      await screen.findByText(/Incremental indexing is disabled/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Add missing jobs/i })).toBeDisabled();
  });

  it("disables the duplicate checkbox while a run is queued", async () => {
    vi.mocked(api.embeddingStatus).mockResolvedValue({
      available: true,
      current_db_total: 10,
      run: {
        id: "run-queued",
        status: "queued",
        mode: "full",
        unique_only: true,
        embed_source: "ollama",
        embed_model: "all-minilm",
        embed_dims: 384,
        db_total_snapshot: 10,
        selection_total: 5,
        target_total: 5,
        processed: 0,
        indexed: 0,
        failed: 0,
        index_alias: "jobseeker_jobs_active",
        physical_index_name: "jobseeker_jobs_run_queued",
        celery_task_id: "celery-queued",
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
    });

    render(<ImportContent />);

    const checkbox = await screen.findByRole("checkbox", {
      name: /Index only unique jobs/i,
    });
    expect(checkbox).toBeChecked();
    expect(checkbox).toBeDisabled();
  });

  it("disables the duplicate checkbox while a run is running", async () => {
    vi.mocked(api.embeddingStatus).mockResolvedValue({
      available: true,
      current_db_total: 10,
      run: {
        id: "run-running",
        status: "running",
        mode: "full",
        unique_only: false,
        embed_source: "ollama",
        embed_model: "all-minilm",
        embed_dims: 384,
        db_total_snapshot: 10,
        selection_total: 10,
        target_total: 10,
        processed: 3,
        indexed: 3,
        failed: 0,
        index_alias: "jobseeker_jobs_active",
        physical_index_name: "jobseeker_jobs_run_running",
        celery_task_id: "celery-running",
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
    });

    render(<ImportContent />);

    const checkbox = await screen.findByRole("checkbox", {
      name: /Index only unique jobs/i,
    });
    expect(checkbox).not.toBeChecked();
    expect(checkbox).toBeDisabled();
  });

  it("submits the exact duplicate choice selected while idle", async () => {
    const user = userEvent.setup();
    vi.mocked(api.embeddingStatus).mockResolvedValue({
      available: true,
      current_db_total: 10,
      run: null,
      active_run: null,
      active_index_name: null,
      active_indexed_documents: 0,
      current_config_matches_active: false,
      reindex_required: true,
      legacy_indices: [],
    });
    vi.mocked(api.syncEmbeddings).mockResolvedValue({
      id: "run-unique",
      status: "queued",
      mode: "full",
      unique_only: true,
      embed_source: "ollama",
      embed_model: "all-minilm",
      embed_dims: 384,
      db_total_snapshot: 10,
      selection_total: 5,
      target_total: 5,
      processed: 0,
      indexed: 0,
      failed: 0,
      index_alias: "jobseeker_jobs_active",
      physical_index_name: "jobseeker_jobs_run_unique",
      celery_task_id: "celery-unique",
      error_message: null,
      started_at: null,
      finished_at: null,
      updated_at: null,
      activated_at: null,
    });

    render(<ImportContent />);

    const checkbox = await screen.findByRole("checkbox", {
      name: /Index only unique jobs/i,
    });
    await user.click(checkbox);
    expect(checkbox).toBeChecked();

    await user.click(screen.getByRole("button", { name: /Re-index all/i }));

    await waitFor(() => {
      expect(api.syncEmbeddings).toHaveBeenCalledWith({
        mode: "full",
        unique_only: true,
      });
    });
  });
});
