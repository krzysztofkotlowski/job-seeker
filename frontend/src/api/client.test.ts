import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../auth/tokenProvider", () => ({
  getTokenForRequest: vi.fn().mockResolvedValue(null),
}));

import { api } from "./client";

function streamFromChunks(chunks: string[]) {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

describe("api.resumeSummarizeStream", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("reassembles split SSE lines without dropping summary chunks", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        streamFromChunks([
          'data: {"chunk":"Strong fit',
          ' for backend roles."}\n\n',
          'data: {"chunk":" Add SQL examples."}\n\n',
          'data: {"done":true,"recommendations":[{"title":"Tailor CV"}]}',
        ]),
        {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        },
      ),
    ) as typeof fetch;

    const chunks: string[] = [];
    const result = await api.resumeSummarizeStream(
      {
        extracted_skills: ["Python"],
        matches: [],
        by_category: [],
      },
      (chunk) => {
        chunks.push(chunk);
      },
    );

    expect(chunks).toEqual([
      "Strong fit for backend roles.",
      " Add SQL examples.",
    ]);
    expect(result.summary).toBe("Strong fit for backend roles. Add SQL examples.");
    expect(result.recommendations).toEqual([{ title: "Tailor CV" }]);
  });
});
