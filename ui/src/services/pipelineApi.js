/** Pipeline API calls for starting runs and checking backend status. */
import { API_BASE, fetchWithTimeout, getAuthHeaders, handleResponse } from "./core/http.js";

export async function runPipeline(payload) {
  const res = await fetchWithTimeout(`${API_BASE}/pipeline/run`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(payload)
  });
  return handleResponse(res);
}

export async function getPipelineStatus() {
  const res = await fetchWithTimeout(`${API_BASE}/pipeline/status`, {
    method: "GET",
    headers: getAuthHeaders()
  });
  return handleResponse(res);
}

export async function getPipelineResults() {
  const res = await fetchWithTimeout(`${API_BASE}/pipeline/results`, {
    method: "GET",
    headers: getAuthHeaders(),
    cache: "no-store"
  });
  return handleResponse(res);
}

export async function downloadPipelineResultFile(fileName) {
  const encodedName = encodeURIComponent(String(fileName || "").trim());
  const res = await fetchWithTimeout(`${API_BASE}/pipeline/results/download/${encodedName}`, {
    method: "GET",
    headers: getAuthHeaders(),
    cache: "no-store"
  });

  if (!res.ok) {
    let message = `Request failed with status ${res.status}`;
    try {
      const data = await res.json();
      message = data?.detail || data?.message || message;
    } catch (error) {
      message = message;
    }
    throw new Error(message);
  }

  return {
    blob: await res.blob(),
    fileName: fileName || "pipeline-results.csv"
  };
}
