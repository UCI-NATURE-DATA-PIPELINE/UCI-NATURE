/** Statistics API calls for analytics charts and summary counters. */
import { API_BASE, fetchWithTimeout, getAuthHeaders, handleResponse } from "./core/http.js";

export async function getStatisticsSummary() {
  const res = await fetchWithTimeout(`${API_BASE}/statistics/summary`, {
    method: "GET",
    headers: getAuthHeaders(),
    cache: "no-store"
  });
  return handleResponse(res);
}
