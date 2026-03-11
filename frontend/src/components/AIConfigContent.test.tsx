import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { AIConfigContent } from "./AIConfigContent";
import { api } from "../api/client";
import { ToastProvider } from "../contexts/ToastContext";

vi.mock("../api/client", () => ({
  api: {
    aiListModels: vi.fn().mockResolvedValue({
      models: [
        {
          name: "qwen2.5:3b",
          model: "qwen2.5:3b",
          role: "chat",
          available: true,
          active: true,
          supported: true,
          status: "active",
          details: { status: "active" },
        },
        {
          name: "all-minilm",
          model: "all-minilm",
          role: "embedding",
          available: false,
          active: false,
          supported: true,
          status: "not_installed",
          details: { status: "not installed" },
        },
      ],
    }),
    aiEnsureModel: vi.fn().mockResolvedValue({ status: "ok" }),
    aiGetConfig: vi.fn().mockResolvedValue({
      provider: "ollama",
      openai_llm_model: "gpt-4o-mini",
      embed_source: "ollama",
      api_key_set: false,
      llm_model: "qwen2.5:3b",
      embed_model: "all-minilm",
      embed_dims: 384,
      temperature: 0.3,
      max_output_tokens: 1024,
    }),
    aiGetMetrics: vi.fn().mockResolvedValue({
      total_requests: 0,
      avg_latency_ms: null,
      total_input_tokens: 0,
      total_output_tokens: 0,
      by_model: [],
      last_7_days: true,
    }),
    aiUpdateConfig: vi.fn().mockResolvedValue({
      provider: "openai",
      openai_llm_model: "gpt-4o-mini",
      embed_source: "openai",
      api_key_set: true,
      llm_model: "",
      embed_model: "",
      embed_dims: 1536,
      temperature: 0.3,
      max_output_tokens: 1024,
    }),
    aiValidateOpenAIKey: vi.fn().mockResolvedValue({ valid: true }),
  },
}));

function renderWithProviders() {
  return render(
    <ToastProvider>
      <AIConfigContent />
    </ToastProvider>,
  );
}

describe("AIConfigContent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("saves OpenAI config without sending an empty llm_model", async () => {
    const user = userEvent.setup();
    renderWithProviders();

    await waitFor(() => {
      expect(api.aiGetConfig).toHaveBeenCalled();
    });

    const openaiToggle = screen.getByRole("button", { name: /OpenAI API/i });
    await user.click(openaiToggle);

    const apiKeyInput = screen.getByLabelText(/OpenAI API key/i);
    await user.type(apiKeyInput, "sk-test-key");

    const saveButton = screen.getByRole("button", { name: /^Save$/ });
    await user.click(saveButton);

    await waitFor(() => {
      expect(api.aiUpdateConfig).toHaveBeenCalled();
    });

    const payload = (api.aiUpdateConfig as ReturnType<typeof vi.fn>).mock
      .calls[0][0];
    expect(payload.provider).toBe("openai");
    expect(payload.openai_api_key).toBe("sk-test-key");
    expect(payload.openai_llm_model).toBe("gpt-4o-mini");
    expect(payload.embed_source).toBe("ollama");
    expect(payload).not.toHaveProperty("llm_model");
    expect(payload.embed_model).toBe("all-minilm");
  });

  it("shows resolved embedding dims from the saved config", async () => {
    renderWithProviders();

    expect(
      await screen.findByText(/Resolved embedding dims:\s*384/i),
    ).toBeInTheDocument();
  });

  it("ensures both selected self-hosted models before saving", async () => {
    const user = userEvent.setup();
    (api.aiUpdateConfig as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      provider: "ollama",
      openai_llm_model: "gpt-4o-mini",
      embed_source: "ollama",
      api_key_set: false,
      llm_model: "qwen2.5:3b",
      embed_model: "all-minilm",
      embed_dims: 384,
      temperature: 0.3,
      max_output_tokens: 1024,
    });

    renderWithProviders();

    await waitFor(() => {
      expect(api.aiGetConfig).toHaveBeenCalled();
    });

    await user.click(screen.getByRole("button", { name: /^Save$/ }));

    await waitFor(() => {
      expect(api.aiEnsureModel).toHaveBeenCalledTimes(2);
      expect(api.aiUpdateConfig).toHaveBeenCalled();
    });

    expect(api.aiEnsureModel).toHaveBeenNthCalledWith(1, "qwen2.5:3b");
    expect(api.aiEnsureModel).toHaveBeenNthCalledWith(2, "all-minilm");
  });

  it("renders supported self-hosted catalog models with availability labels", async () => {
    renderWithProviders();

    expect(
      await screen.findByText("qwen2.5:3b · active"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("all-minilm · not installed"),
    ).toBeInTheDocument();
  });
});
