import type { Dashboard } from "./types";

// Empty in production: the API is served from the same origin as the app.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export async function fetchDashboard(cutoff: string, signal?: AbortSignal): Promise<Dashboard> {
  const response = await fetch(
    `${API_BASE}/api/v1/dashboard?cutoff=${encodeURIComponent(cutoff)}`,
    { signal },
  );
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the status text.
    }
    throw new Error(`Dashboard request failed (${response.status}): ${detail}`);
  }
  return response.json();
}
