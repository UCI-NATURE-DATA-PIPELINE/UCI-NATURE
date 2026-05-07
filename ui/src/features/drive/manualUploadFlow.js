/** Manual upload flow for the Upload page.
 *
 * Wires the manualUpload.html partial to the backend `/api/upload/images`
 * endpoint:
 *   - Drag/drop + Browse files into a queue (validates wildlife image types)
 *   - Sends FormData to the backend with the chosen camera site
 *   - Streams progress + success/error feedback into the existing UI
 *
 * Designed to be initialized once after the feature markup is loaded. Re-render
 * the controls (e.g. backend status banner) by calling refresh().
 */
import { appState } from "../../state/appState.js";
import { uploadStagedImages } from "../../services/api.js";

const ACCEPTED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".tif", ".tiff"];

function hasImageExtension(name) {
  const lower = String(name || "").toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function isImageFile(file) {
  if (!file) return false;
  if (file.type && file.type.startsWith("image/")) return true;
  return hasImageExtension(file.name);
}

function formatBytes(value) {
  const num = Number(value) || 0;
  if (num <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let n = num;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  const decimals = n >= 10 || i === 0 ? 0 : 1;
  return `${n.toFixed(decimals)} ${units[i]}`;
}

function getById(id) {
  return document.getElementById(id);
}

export function createManualUploadFlow(app) {
  const state = {
    files: [],
    cameraLocation: "Site 1",
    isUploading: false,
    progress: 0,
    error: "",
    lastResult: null
  };

  let bound = false;

  function getElements() {
    return {
      manualRoot: getById("upload-manual"),
      zone: getById("upload-zone"),
      input: getById("upload-file-input"),
      browseBtn: getById("upload-browse-btn"),
      list: getById("upload-queue-list"),
      meta: getById("upload-queue-meta"),
      total: getById("upload-manual-total"),
      sizeStat: getById("upload-manual-size"),
      siteStat: getById("upload-manual-site"),
      statusStat: getById("upload-manual-status"),
      barInfo: getById("upload-action-bar-info"),
      startBtn: getById("upload-start-btn"),
      clearBtn: getById("upload-clear-btn"),
      result: getById("upload-result-card"),
      resultMessage: getById("upload-result-message"),
      resultDetails: getById("upload-result-details"),
      backendBanner: getById("upload-backend-banner")
    };
  }

  function readSelectedSite() {
    const card = document.querySelector("#upload-manual .loc-select-card.selected");
    const name = card?.dataset?.uploadSite
      || card?.querySelector(".loc-select-name")?.textContent?.trim();
    return (name || "Site 1").trim();
  }

  function totalBytes() {
    return state.files.reduce((sum, file) => sum + (Number(file.size) || 0), 0);
  }

  function isBackendConnected() {
    return Boolean(appState.backendHealth?.connected);
  }

  function statusLabel() {
    if (state.isUploading) return "Uploading";
    if (state.error) return "Error";
    if (state.lastResult) return "Uploaded";
    return state.files.length ? "Ready" : "Ready";
  }

  function renderSummary() {
    const els = getElements();
    state.cameraLocation = readSelectedSite();
    if (els.total) els.total.textContent = String(state.files.length);
    if (els.sizeStat) els.sizeStat.textContent = state.files.length ? formatBytes(totalBytes()) : "—";
    if (els.siteStat) els.siteStat.textContent = state.cameraLocation;
    if (els.statusStat) els.statusStat.textContent = statusLabel();
    if (els.meta) {
      if (state.isUploading) {
        els.meta.textContent = `Uploading ${state.files.length} file(s)…`;
      } else if (state.lastResult) {
        const count = state.lastResult.uploaded_count ?? state.files.length;
        els.meta.textContent = `${count} file(s) saved · ${formatBytes(state.lastResult.total_bytes || 0)}`;
      } else if (state.files.length) {
        els.meta.textContent = `${state.files.length} file(s) · ${formatBytes(totalBytes())}`;
      } else {
        els.meta.textContent = "No files selected yet";
      }
    }
    if (els.barInfo) {
      if (state.isUploading) {
        els.barInfo.innerHTML = `Uploading <strong>${state.files.length} file(s)</strong> to backend staging… ${state.progress}%`;
      } else if (state.lastResult) {
        const count = state.lastResult.uploaded_count ?? state.files.length;
        const skipped = state.lastResult.skipped_count || 0;
        const skippedNote = skipped ? ` · skipped ${skipped} unsupported file(s)` : "";
        els.barInfo.innerHTML = `Processing complete: <strong>${count} image(s)</strong> staged${skippedNote}.`;
      } else if (state.error) {
        els.barInfo.textContent = state.error;
      } else if (state.files.length) {
        els.barInfo.innerHTML = `<strong>${state.files.length} file(s)</strong> ready · ${formatBytes(totalBytes())} · Site: ${state.cameraLocation}`;
      } else {
        els.barInfo.textContent = "Drop or browse wildlife camera images to begin.";
      }
    }
  }

  function renderQueue() {
    const els = getElements();
    if (!els.list) return;
    els.list.innerHTML = "";

    if (!state.files.length) {
      const empty = document.createElement("div");
      empty.className = "upload-queue-empty";
      empty.textContent = state.lastResult
        ? "Queue cleared after upload. Add another batch to continue."
        : "No images selected yet. Drop wildlife camera images above or click Browse Files.";
      els.list.appendChild(empty);
      return;
    }

    const progressClass = state.isUploading
      ? "active"
      : state.lastResult
        ? "done"
        : "";
    const fillWidth = state.isUploading
      ? state.progress
      : state.lastResult
        ? 100
        : 0;
    const pillClass = state.lastResult
      ? "pill-green"
      : state.isUploading
        ? "pill-yellow"
        : state.error
          ? "pill-red"
          : "pill-slate";
    const pillText = state.lastResult
      ? "✓ Uploaded"
      : state.isUploading
        ? "Uploading…"
        : state.error
          ? "Failed"
          : "Pending";

    state.files.forEach((file) => {
      const row = document.createElement("div");
      row.className = "upload-queue-item";
      row.innerHTML = `
        <div class="queue-file-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#3182CE" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <circle cx="8.5" cy="8.5" r="1.5"/>
            <polyline points="21 15 16 10 5 21"/>
          </svg>
        </div>
        <div>
          <div class="queue-file-name"></div>
          <div class="queue-file-meta"></div>
        </div>
        <span class="queue-location-tag"></span>
        <span class="queue-size-text"></span>
        <div class="queue-prog-wrap">
          <div class="queue-prog-bar"><div class="queue-prog-fill ${progressClass}" style="width:${fillWidth}%"></div></div>
          <div class="queue-prog-pct">${fillWidth}%</div>
        </div>
        <span class="status-pill ${pillClass}">${pillText}</span>
      `;
      // Use textContent to safely render user-supplied filenames.
      row.querySelector(".queue-file-name").textContent = file.name;
      row.querySelector(".queue-file-meta").textContent = `${formatBytes(file.size)} · ${state.cameraLocation}`;
      row.querySelector(".queue-location-tag").textContent = state.cameraLocation;
      row.querySelector(".queue-size-text").textContent = formatBytes(file.size);
      els.list.appendChild(row);
    });
  }

  function renderControls() {
    const els = getElements();
    const backendDown = !isBackendConnected();
    if (els.backendBanner) {
      els.backendBanner.hidden = !backendDown;
    }
    if (els.startBtn) {
      els.startBtn.disabled = state.isUploading || !state.files.length || backendDown;
    }
    if (els.clearBtn) {
      els.clearBtn.disabled = state.isUploading
        || (!state.files.length && !state.lastResult && !state.error);
    }
  }

  function renderResult() {
    const els = getElements();
    if (!els.result) return;
    if (state.error) {
      els.result.hidden = false;
      els.result.classList.remove("upload-result-success");
      els.result.classList.add("upload-result-error");
      if (els.resultMessage) els.resultMessage.textContent = state.error;
      if (els.resultDetails) {
        els.resultDetails.textContent = isBackendConnected()
          ? "Fix the issue above and try the upload again."
          : "Backend is not connected. Please start the backend and try again.";
      }
      return;
    }
    if (state.lastResult) {
      els.result.hidden = false;
      els.result.classList.add("upload-result-success");
      els.result.classList.remove("upload-result-error");
      const count = state.lastResult.uploaded_count ?? 0;
      const skipped = state.lastResult.skipped_count || 0;
      const stagingDir = state.lastResult.staging_dir || "backend staging";
      const totalBytesValue = state.lastResult.total_bytes || 0;
      if (els.resultMessage) {
        els.resultMessage.textContent = `Upload complete · ${count} image(s) saved`;
      }
      if (els.resultDetails) {
        const skippedNote = skipped ? ` Skipped ${skipped} unsupported file(s).` : "";
        els.resultDetails.textContent =
          `${formatBytes(totalBytesValue)} written to ${stagingDir}.${skippedNote}`
          + ` Open the Run Model page to process the staged images. Results will be exported as a CSV.`;
      }
      return;
    }
    els.result.hidden = true;
  }

  function render() {
    renderSummary();
    renderQueue();
    renderControls();
    renderResult();
  }

  function dedupeKey(file) {
    return `${file.name}|${file.size}|${file.lastModified || 0}`;
  }

  function addFiles(fileList) {
    if (!fileList || !fileList.length) return;
    const incoming = Array.from(fileList);
    const accepted = incoming.filter(isImageFile);
    const rejectedCount = incoming.length - accepted.length;
    if (!accepted.length) {
      app.showToast("No supported wildlife images found in selection (JPG, PNG, TIFF).", "warn");
      return;
    }
    const map = new Map(state.files.map((file) => [dedupeKey(file), file]));
    accepted.forEach((file) => {
      const key = dedupeKey(file);
      if (!map.has(key)) map.set(key, file);
    });
    state.files = Array.from(map.values());
    state.error = "";
    state.lastResult = null;
    state.progress = 0;
    if (rejectedCount > 0) {
      app.showToast(`Skipped ${rejectedCount} non-image file(s).`, "warn");
    }
    render();
  }

  function clearFiles() {
    state.files = [];
    state.error = "";
    state.lastResult = null;
    state.progress = 0;
    render();
  }

  async function startUpload() {
    if (state.isUploading || !state.files.length) return;
    if (!isBackendConnected()) {
      app.showToast("Backend is not connected. Please start the backend and try again.", "warn");
      return;
    }
    state.isUploading = true;
    state.progress = 0;
    state.error = "";
    state.lastResult = null;
    render();

    try {
      const result = await uploadStagedImages(state.files, {
        cameraLocation: state.cameraLocation,
        onProgress: ({ percent }) => {
          const next = Math.max(0, Math.min(100, Number(percent) || 0));
          if (next !== state.progress) {
            state.progress = next;
            renderSummary();
            renderQueue();
          }
        }
      });
      state.lastResult = result || {};
      state.progress = 100;
      const count = state.lastResult.uploaded_count ?? state.files.length;
      app.showToast(`Upload complete · ${count} image(s) saved`, "success");
      // Reset queue but keep the result card so the user has a confirmation trail.
      state.files = [];
    } catch (error) {
      const message = error?.message || "Upload failed";
      state.error = message;
      app.showToast(message, "warn");
    } finally {
      state.isUploading = false;
      render();
    }
  }

  function handleZoneDragOver(event) {
    event.preventDefault();
    event.currentTarget.classList.add("drag-over");
  }
  function handleZoneDragLeave(event) {
    event.currentTarget.classList.remove("drag-over");
  }
  function handleZoneDrop(event) {
    event.preventDefault();
    event.currentTarget.classList.remove("drag-over");
    addFiles(event.dataTransfer?.files);
  }
  function handleZoneClick(event) {
    if (event.target.closest("#upload-browse-btn")) return;
    getElements().input?.click();
  }
  function handleZoneKeydown(event) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      getElements().input?.click();
    }
  }
  function handleBrowseClick(event) {
    event.preventDefault();
    event.stopPropagation();
    getElements().input?.click();
  }
  function handleInputChange(event) {
    addFiles(event.target?.files);
    if (event.target) event.target.value = "";
  }
  function handleSiteChange() {
    state.cameraLocation = readSelectedSite();
    render();
  }

  function bindEvents() {
    const els = getElements();
    if (bound || !els.zone || !els.input) return false;
    els.zone.addEventListener("dragover", handleZoneDragOver);
    els.zone.addEventListener("dragleave", handleZoneDragLeave);
    els.zone.addEventListener("drop", handleZoneDrop);
    els.zone.addEventListener("click", handleZoneClick);
    els.zone.addEventListener("keydown", handleZoneKeydown);
    els.input.addEventListener("change", handleInputChange);
    els.browseBtn?.addEventListener("click", handleBrowseClick);
    els.startBtn?.addEventListener("click", () => { void startUpload(); });
    els.clearBtn?.addEventListener("click", clearFiles);
    document.querySelectorAll("#upload-manual .loc-select-card").forEach((card) => {
      // Run after the existing selectLocCard() handler so .selected is up to date.
      card.addEventListener("click", () => window.setTimeout(handleSiteChange, 0));
    });
    bound = true;
    return true;
  }

  function initialize() {
    if (!bindEvents()) return;
    state.cameraLocation = readSelectedSite();
    render();
  }

  function refresh() {
    if (!bound) return;
    render();
  }

  return { initialize, refresh, startUpload, clearFiles };
}
