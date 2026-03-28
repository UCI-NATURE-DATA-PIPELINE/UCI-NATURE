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
    return "http://127.0.0.1:8000";
  }

  return normalizeBaseUrl(origin);
}

const BACKEND_BASE = resolveBackendBase();
const API_BASE = `${BACKEND_BASE}/api`;

function getStoredToken() {
  return localStorage.getItem("token") || "";
}

function getAuthHeaders() {
  const headers = {
    "Content-Type": "application/json"
  };
  const token = getStoredToken();

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return headers;
}

async function handleResponse(res) {
  let data = null;

  try {
    data = await res.json();
  } catch (e) {
    data = null;
  }

  if (!res.ok) {
    const message =
      data?.detail ||
      data?.message ||
      `Request failed with status ${res.status}`;
    throw new Error(message);
  }

  return data;
}

export async function loginUser(email, project) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ email, project })
  });

  return handleResponse(res);
}

export async function getCurrentUser() {
  const res = await fetch(`${API_BASE}/auth/me`, {
    method: "GET",
    headers: getAuthHeaders(),
    cache: "no-store"
  });

  return handleResponse(res);
}

export async function getGoogleAuthStartUrl() {
  const res = await fetch(`${API_BASE}/auth/google/start`, {
    method: "GET",
    headers: getAuthHeaders(),
    cache: "no-store"
  });

  const data = await handleResponse(res);
  return data?.auth_url || "";
}

export async function getGoogleAuthStatus() {
  const res = await fetch(`${API_BASE}/auth/google/me`, {
    method: "GET",
    headers: getAuthHeaders(),
    cache: "no-store"
  });

  return handleResponse(res);
}

export async function logoutGoogleAuth() {
  const res = await fetch(`${API_BASE}/auth/google/logout`, {
    method: "POST",
    headers: getAuthHeaders()
  });

  return handleResponse(res);
}

export async function connectDrive(drive_name, drive_email) {
  const res = await fetch(`${API_BASE}/drive/connect`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ drive_name, drive_email })
  });

  return handleResponse(res);
}

export async function getDriveStatus() {
  const res = await fetch(`${API_BASE}/drive/status`, {
    method: "GET",
    headers: getAuthHeaders(),
    cache: "no-store"
  });

  return handleResponse(res);
}

export async function getDriveFolders() {
  const res = await fetch(`${API_BASE}/drive/folders`, {
    method: "GET",
    headers: getAuthHeaders(),
    cache: "no-store"
  });

  return handleResponse(res);
}

export async function saveSelectedDriveFolder(folder_id, folder_name, camera_location = null, max_files = null) {
  const res = await fetch(`${API_BASE}/drive/select-folder`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ folder_id, folder_name, camera_location, max_files })
  });

  return handleResponse(res);
}

export async function getSelectedDriveFolder() {
  const res = await fetch(`${API_BASE}/drive/selected-folder`, {
    method: "GET",
    headers: getAuthHeaders(),
    cache: "no-store"
  });

  return handleResponse(res);
}

export async function syncSelectedDriveFolder(max_files = null) {
  const res = await fetch(`${API_BASE}/drive/sync`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ max_files })
  });

  return handleResponse(res);
}

export async function getDriveSyncStatus() {
  const res = await fetch(`${API_BASE}/drive/sync-status`, {
    method: "GET",
    headers: getAuthHeaders(),
    cache: "no-store"
  });

  return handleResponse(res);
}

export async function getDashboardSummary() {
  const res = await fetch(`${API_BASE}/dashboard/summary`, {
    method: "GET",
    headers: getAuthHeaders()
  });

  return handleResponse(res);
}

export async function runPipeline(payload) {
  const res = await fetch(`${API_BASE}/pipeline/run`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(payload)
  });

  return handleResponse(res);
}

export async function getPipelineStatus() {
  const res = await fetch(`${API_BASE}/pipeline/status`, {
    method: "GET",
    headers: getAuthHeaders()
  });

  return handleResponse(res);
}

export async function getReviewItems() {
  const res = await fetch(`${API_BASE}/review/items`, {
    method: "GET",
    headers: getAuthHeaders()
  });

  return handleResponse(res);
}

export async function getValidationIssues() {
  const res = await fetch(`${API_BASE}/validate/issues`, {
    method: "GET",
    headers: getAuthHeaders()
  });

  return handleResponse(res);
}

export async function startExport() {
  const res = await fetch(`${API_BASE}/export/start`, {
    method: "POST",
    headers: getAuthHeaders()
  });

  return handleResponse(res);
}
