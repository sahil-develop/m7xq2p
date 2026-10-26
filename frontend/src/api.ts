import type { Dashboard } from "./types";

// Empty when the API is served from the same origin as the app (Docker image); set
// VITE_API_BASE_URL to the API origin when the SPA is hosted separately (Vercel).
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

export async function fetchDashboard(cutoff: string, signal?: AbortSignal): Promise<Dashboard> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/dashboard?cutoff=${encodeURIComponent(cutoff)}`, {
      signal,
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    // fetch only rejects on network failure; its own message ("Failed to fetch") is unhelpful.
    throw new Error("The API could not be reached. Check your connection and retry.");
  }
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
