import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import App from "./App";

vi.mock("./api/client", () => {
  return {
    api: {
      createBackup: vi.fn().mockResolvedValue(new Blob(["test"], { type: "application/sql" })),
    },
  };
});

describe("App backup button", () => {
  it("renders Backup DB button", () => {
    render(<App />);
    expect(screen.getByText("Backup DB")).toBeInTheDocument();
  });
});

