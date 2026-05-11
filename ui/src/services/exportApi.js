/** Export API calls for loading generated export artifacts from the backend. */
import { API_BASE, fetchWithTimeout, getAuthHeaders, handleResponse } from "./core/http.js";

export async function startExport(options = {}) {
  const res = await fetchWithTimeout(`${API_BASE}/export/start`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(options)
  });
  return handleResponse(res);
}

/**
 * Triggers a CSV download for a single export artifact file.
 * Calls GET /api/pipeline/results/download/{file_name} and saves to disk.
 */
export async function downloadExportFile(fileName, token = "") {
  const res = await fetchWithTimeout(
    `${API_BASE}/pipeline/results/download/${encodeURIComponent(fileName)}`,
    { method: "GET", headers: getAuthHeaders(token) }
  );
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data?.detail || `Download failed: ${res.status}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
