import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { vi } from "vitest";

import { ImportPage } from "./ImportPage";
import { api } from "../api/client";

vi.mock("../api/client", () => ({
  api: {
    importStatus: vi.fn().mockResolvedValue({
      running: false,
      tasks: [{ source: "justjoin.it", status: "done", total: 10, processed: 10, imported: 8, skipped: 2, errors: 0, error_log: [], pending: 0, started_at: null, updated_at: null }],
    }),
    importStart: vi.fn().mockResolvedValue({ message: "Import started", running: true }),
    importStartSource: vi.fn().mockResolvedValue({ message: "Import started", running: true }),
    importCancel: vi.fn().mockResolvedValue({ message: "Cancel requested" }),
    embeddingStatus: vi.fn().mockResolvedValue({ available: false, indexed: 0, total: 0, syncing: false }),
    syncEmbeddingsStream: vi.fn().mockResolvedValue({ indexed: 0, total: 0 }),
  },
}));

describe("ImportPage", () => {
  it("shows import task status", async () => {
    render(
      <BrowserRouter>
        <ImportPage />
      </BrowserRouter>,
    );

    await waitFor(() => {
      expect(api.importStatus).toHaveBeenCalled();
    });

    expect(await screen.findByText(/Completed/i)).toBeInTheDocument();
  });

  it("shows embedding section", async () => {
    render(
      <BrowserRouter>
        <ImportPage />
      </BrowserRouter>,
    );

    await waitFor(() => {
      expect(api.embeddingStatus).toHaveBeenCalled();
    });

    expect(await screen.findByText(/Vector Index \(RAG\)/i)).toBeInTheDocument();
  });
});

