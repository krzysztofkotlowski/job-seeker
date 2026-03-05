import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { ImportPage } from "./ImportPage";
import { api } from "../api/client";

vi.mock("../api/client", () => {
  return {
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
            started_at: null,
            updated_at: null,
          },
        ],
      }),
      importStart: vi.fn().mockResolvedValue({ message: "Import started", running: true }),
      importStartSource: vi.fn().mockResolvedValue({ message: "Import started", running: true }),
      importCancel: vi.fn().mockResolvedValue({ message: "Cancel requested" }),
    },
  };
});

describe("ImportPage", () => {
  it("shows import task status", async () => {
    render(<ImportPage />);

    await waitFor(() => {
      expect(api.importStatus).toHaveBeenCalled();
    });

    expect(await screen.findByText(/justjoin\.it/i)).toBeInTheDocument();
    expect(screen.getByText(/done/i)).toBeInTheDocument();
  });
});

