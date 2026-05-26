// /** Review API calls for loading manual-review queue items. */
// import { API_BASE, fetchWithTimeout, getAuthHeaders, handleResponse } from "./core/http.js";

// export async function getReviewItems() {
//   const res = await fetchWithTimeout(`${API_BASE}/review/items`, {
//     method: "GET",
//     headers: getAuthHeaders()
//   });
//   return handleResponse(res);
// }

/** Review API calls for loading manual-review queue items and saving decisions. */
import { API_BASE, fetchWithTimeout, getAuthHeaders, handleResponse } from "./core/http.js";

export async function getReviewItems() {
  const res = await fetchWithTimeout(`${API_BASE}/review/items`, {
    method: "GET",
    headers: getAuthHeaders()
  });
  return handleResponse(res);
}

export async function saveReviewDecision({ filepath, reviewStatus, reviewedSpecies = "", reviewReason = "" }) {
  const res = await fetchWithTimeout(`${API_BASE}/review/save`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({
      filepath,
      review_status: reviewStatus,
      reviewed_species: reviewedSpecies,
      review_reason: reviewReason
    })
  });
  return handleResponse(res);
}

export async function applyReviewDecisions(options = {}) {
  const res = await fetchWithTimeout(`${API_BASE}/review/apply`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({
      burst_seconds: options.burstSeconds ?? null,
      burst_export: options.burstExport ?? null,
      exclude_humans: options.excludeHumans ?? null
    })
  });
  return handleResponse(res);
}