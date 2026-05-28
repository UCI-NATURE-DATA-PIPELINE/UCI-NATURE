/** Dashboard API calls for summary cards and activity data. */
import { API_BASE, fetchWithTimeout, getAuthHeaders, handleResponse } from "./core/http.js";

export async function getDashboardSummary() {
  const res = await fetchWithTimeout(`${API_BASE}/dashboard/summary`, {
    method: "GET",
    headers: getAuthHeaders()
  });
  return handleResponse(res);
}

export async function getDashboardSpeciesHistogram() {
  const res = await fetchWithTimeout(`${API_BASE}/dashboard/species-histogram`, {
    method: "GET",
    headers: getAuthHeaders()
  });
  return handleResponse(res);
}
