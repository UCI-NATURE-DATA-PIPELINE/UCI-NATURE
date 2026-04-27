/** Export API calls for loading generated export artifacts from the backend. */
import { API_BASE, fetchWithTimeout, getAuthHeaders, handleResponse } from "./core/http.js";

export async function startExport() {
  const res = await fetchWithTimeout(`${API_BASE}/export/start`, {
    method: "POST",
    headers: getAuthHeaders()
  });
  return handleResponse(res);
}
