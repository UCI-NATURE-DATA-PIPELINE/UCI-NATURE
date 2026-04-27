/** Review API calls for loading manual-review queue items. */
import { API_BASE, fetchWithTimeout, getAuthHeaders, handleResponse } from "./core/http.js";

export async function getReviewItems() {
  const res = await fetchWithTimeout(`${API_BASE}/review/items`, {
    method: "GET",
    headers: getAuthHeaders()
  });
  return handleResponse(res);
}
