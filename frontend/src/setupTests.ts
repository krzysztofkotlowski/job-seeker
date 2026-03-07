import "@testing-library/jest-dom";
import { vi } from "vitest";

// Mock auth config fetch so AuthProvider gets enabled: false in tests
const originalFetch = globalThis.fetch;
globalThis.fetch = vi.fn((input: RequestInfo | URL) => {
  const url =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.href
        : (input as Request).url;
  if (url.includes("/api/v1/auth/config")) {
    return Promise.resolve(new Response(JSON.stringify({ enabled: false })));
  }
  return originalFetch(input);
}) as typeof fetch;
