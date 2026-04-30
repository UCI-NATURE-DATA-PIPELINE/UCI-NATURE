/** Google Drive API calls for connection, folder selection, and sync status. */
import { API_BASE, fetchWithTimeout, getAuthHeaders, handleResponse } from "./core/http.js";

export async function connectDrive(drive_name, drive_email) {
  const res = await fetchWithTimeout(`${API_BASE}/drive/connect`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ drive_name, drive_email })
  });
  return handleResponse(res);
}

export async function getDriveStatus() {
  const res = await fetchWithTimeout(`${API_BASE}/drive/status`, {
    method: "GET",
    headers: getAuthHeaders(),
    cache: "no-store"
  });
  return handleResponse(res);
}

export async function getDriveFolders() {
  const res = await fetchWithTimeout(`${API_BASE}/drive/folders`, {
    method: "GET",
    headers: getAuthHeaders(),
    cache: "no-store"
  });
  return handleResponse(res);
}

export async function saveSelectedDriveFolder(folder_id, folder_name, camera_location = null, max_files = null) {
  const res = await fetchWithTimeout(`${API_BASE}/drive/select-folder`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ folder_id, folder_name, camera_location, max_files })
  });
  return handleResponse(res);
}

export async function getSelectedDriveFolder() {
  const res = await fetchWithTimeout(`${API_BASE}/drive/selected-folder`, {
    method: "GET",
    headers: getAuthHeaders(),
    cache: "no-store"
  });
  return handleResponse(res);
}

export async function syncSelectedDriveFolder(max_files = null) {
  const res = await fetchWithTimeout(`${API_BASE}/drive/sync`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ max_files })
  });
  return handleResponse(res);
}

export async function getDriveSyncStatus() {
  const res = await fetchWithTimeout(`${API_BASE}/drive/sync-status`, {
    method: "GET",
    headers: getAuthHeaders(),
    cache: "no-store"
  });
  return handleResponse(res);
}
