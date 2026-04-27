/** Validation API calls for deployment-range and processing checks. */
import { API_BASE, fetchWithTimeout, getAuthHeaders, handleResponse } from "./core/http.js";

export async function getValidationIssues() {
  const res = await fetchWithTimeout(`${API_BASE}/validate/issues`, {
    method: "GET",
    headers: getAuthHeaders()
  });
  return handleResponse(res);
}
