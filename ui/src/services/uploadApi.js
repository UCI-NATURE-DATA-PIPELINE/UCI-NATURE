/** Manual upload API helper for the Upload page. Uses XHR so we can stream
 * upload progress events back to the UI (fetch() doesn't expose upload progress).
 * Goes against the same API_BASE / token flow as the rest of the app. */
import { API_BASE } from "./core/http.js";

// Wildlife camera batches can be large; allow up to 30 minutes per request.
const UPLOAD_TIMEOUT_MS = 30 * 60 * 1000;

function getStoredAuthToken() {
  try {
    return localStorage.getItem("token") || "";
  } catch (error) {
    return "";
  }
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
export function uploadStagedImages(files, { cameraLocation = "", onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    const fileArray = Array.from(files || []);

    if (!fileArray.length) {
      reject(new Error("No files were selected for upload."));
      return;
    }

    fileArray.forEach((file) => {
      formData.append("files", file, file.name);
    });
    if (cameraLocation) {
      formData.append("camera_location", String(cameraLocation));
    }

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/upload/images`);
    xhr.timeout = UPLOAD_TIMEOUT_MS;

    const token = getStoredAuthToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    // NOTE: Do not set Content-Type manually for FormData -- the browser must
    // generate the multipart boundary for FastAPI to parse the request.

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
        resolve(payload || {});
        return;
      }

      const message = (payload && (payload.detail || payload.message))
        || `Upload failed with status ${xhr.status}`;
      reject(new Error(message));
    });

    xhr.addEventListener("error", () => {
      reject(new Error("Network error during upload. Is the backend running?"));
    });
    xhr.addEventListener("timeout", () => {
      reject(new Error("Upload timed out. Try a smaller batch or check the backend."));
    });
    xhr.addEventListener("abort", () => {
      reject(new Error("Upload cancelled."));
    });

    xhr.send(formData);
  });
}
