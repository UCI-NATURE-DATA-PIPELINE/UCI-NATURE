/** Validation API calls for deployment-range and processing checks. */
import { API_BASE, fetchWithTimeout, getAuthHeaders, handleResponse } from "./core/http.js";
export async function getValidationIssues({ startDate = "", endDate = "" } = {}) {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const query = params.toString() ? `?${params.toString()}` : "";
  const res = await fetchWithTimeout(`${API_BASE}/validate/issues${query}`, {
    method: "GET",
    headers: getAuthHeaders()
  });
  return handleResponse(res);
}