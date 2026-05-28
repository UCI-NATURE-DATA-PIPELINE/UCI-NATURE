/** Manual upload API helper for the Upload page. Uses XHR so we can stream
 * upload progress events back to the UI (fetch() doesn't expose upload progress).
 * Goes against the same API_BASE / token flow as the rest of the app. */
import { API_BASE } from "./core/http.js";
import { normalizeCameraSiteName } from "../features/drive/cameraSiteName.js";

// Wildlife camera batches can be large; allow up to 30 minutes per request.
const UPLOAD_TIMEOUT_MS = 30 * 60 * 1000;

function getStoredAuthToken() {
  try {
    return localStorage.getItem("token") || "";
  } catch (error) {
    return "";
  }
}

function sendFormData(url, formData, onProgress, signal) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let settled = false;
    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener?.("abort", abortUpload);
      fn(value);
    };
    const abortUpload = () => xhr.abort();
    if (signal?.aborted) {
      reject(new Error("Upload cancelled."));
      return;
    }
    xhr.open("POST", url);
    xhr.timeout = UPLOAD_TIMEOUT_MS;
    const token = getStoredAuthToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    signal?.addEventListener?.("abort", abortUpload, { once: true });

    xhr.upload.addEventListener("progress", (event) => {
      if (typeof onProgress !== "function") return;
      if (!event.lengthComputable) return;
      const percent = event.total > 0 ? Math.round((event.loaded / event.total) * 100) : 0;
      onProgress({ loaded: event.loaded, total: event.total, percent });
    });

    xhr.addEventListener("load", () => {
      let payload = null;
      try {
        payload = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch (error) {
        payload = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        finish(resolve, payload || {});
        return;
      }
      const message = (payload && (payload.detail || payload.message))
        || `Upload failed with status ${xhr.status}`;
      finish(reject, new Error(message));
    });
    xhr.addEventListener("error", () => finish(reject, new Error("Network error during upload. Is the backend running?")));
    xhr.addEventListener("timeout", () => finish(reject, new Error("Upload timed out. Try a smaller batch or check the backend.")));
    xhr.addEventListener("abort", () => finish(reject, new Error("Upload cancelled.")));

    xhr.send(formData);
  });
}

/**
 * Upload one or more image files to the backend staging directory.
 *
 * @param {File[]|FileList} files - Image files selected by the researcher.
 * @param {object} [options]
 * @param {string} [options.cameraLocation] - Optional per-site subfolder name.
 * @param {(progress: { loaded:number, total:number, percent:number }) => void} [options.onProgress]
 * @returns {Promise<object>} - Backend JSON payload describing saved/skipped files.
 */
export function uploadStagedImages(files, { cameraLocation = "", onProgress, signal } = {}) {
  const fileArray = Array.from(files || []);
  if (!fileArray.length) {
    return Promise.reject(new Error("No files were selected for upload."));
  }
  const formData = new FormData();
  fileArray.forEach((file) => formData.append("files", file, file.name));
  const normalizedCameraLocation = normalizeCameraSiteName(cameraLocation);
  if (normalizedCameraLocation) formData.append("camera_location", normalizedCameraLocation);
  // NOTE: Do not set Content-Type manually for FormData -- the browser must
  // generate the multipart boundary for FastAPI to parse the request.
  return sendFormData(`${API_BASE}/upload/images`, formData, onProgress, signal);
}

/**
 * Upload a single ZIP archive to the backend; the server safely extracts
 * supported image entries into the staging directory.
 *
 * @param {File} zipFile - A ZIP file selected by the researcher.
 * @param {object} [options]
 * @param {string} [options.cameraLocation] - Optional per-site subfolder name.
 * @param {(progress: { loaded:number, total:number, percent:number }) => void} [options.onProgress]
 * @returns {Promise<object>} - Backend JSON payload describing saved/skipped files.
 */
export function uploadStagedZip(zipFile, { cameraLocation = "", onProgress, signal } = {}) {
  if (!zipFile) return Promise.reject(new Error("No ZIP file was selected."));
  const formData = new FormData();
  formData.append("archive", zipFile, zipFile.name);
  const normalizedCameraLocation = normalizeCameraSiteName(cameraLocation);
  if (normalizedCameraLocation) formData.append("camera_location", normalizedCameraLocation);
  return sendFormData(`${API_BASE}/upload/zip`, formData, onProgress, signal);
}
