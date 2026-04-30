/** Backend health API calls for startup checks and header connectivity state. */
import { API_BASE, fetchWithTimeout, handleResponse } from "./core/http.js";

export async function getBackendHealth() {
  const res = await fetchWithTimeout(`${API_BASE}/health`, {
    method: "GET",
    cache: "no-store"
  });
  return handleResponse(res);
}
