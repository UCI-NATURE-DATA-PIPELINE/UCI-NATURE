/** Shared HTTP helpers for backend API modules in the browser-native frontend. */
const DEFAULT_REQUEST_TIMEOUT_MS = 5000;
const DEFAULT_BACKEND_BASE = "http://127.0.0.1:8000";

function normalizeBaseUrl(value) {
  return String(value || "").replace(/\/+$/, "");
}

function resolveBackendBase() {
  const configuredBase =
    window.__UCI_NATURE_CONFIG__?.backendBase ||
    document.querySelector('meta[name="uci-nature-backend-base"]')?.content;

  if (configuredBase) {
    return normalizeBaseUrl(configuredBase);
  }

  const { hostname, origin } = window.location;
  if (hostname === "127.0.0.1" || hostname === "localhost") {
    return DEFAULT_BACKEND_BASE;
  }

  return normalizeBaseUrl(origin);
}

export const BACKEND_BASE = resolveBackendBase();
export const API_BASE = `${BACKEND_BASE}/api`;

function getStoredToken(tokenOverride = "") {
  const normalizedOverride = String(tokenOverride || "").trim();
  if (normalizedOverride) {
    return normalizedOverride;
  }

  return localStorage.getItem("token") || "";
}

export function getAuthHeaders(tokenOverride = "") {
  const headers = {
    "Content-Type": "application/json"
  };
  const token = getStoredToken(tokenOverride);

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return headers;
}

export function fetchWithTimeout(url, options = {}, timeout = DEFAULT_REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeout);

  return fetch(url, {
    ...options,
    signal: controller.signal
  })
    .catch((error) => {
      console.warn("Fetch failed:", url, error);
      throw error;
    })
    .finally(() => window.clearTimeout(timeoutId));
}

export async function handleResponse(res) {
  let data = null;

  try {
    data = await res.json();
  } catch (error) {
    data = null;
  }

  if (!res.ok) {
    throw new Error(data?.detail || data?.message || `Request failed with status ${res.status}`);
  }

  return data;
}
