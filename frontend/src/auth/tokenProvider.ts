/** Module-level token provider for API client. Set by AuthProvider when Keycloak is ready. */
let tokenProvider: (() => Promise<string | null>) | null = null;

export function setTokenProvider(fn: (() => Promise<string | null>) | null): void {
  tokenProvider = fn;
}

export async function getTokenForRequest(): Promise<string | null> {
  if (!tokenProvider) return null;
  return tokenProvider();
}
