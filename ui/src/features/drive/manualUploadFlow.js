/** Manual upload flow for the Upload page.
 *
 * Wires manualUpload.html to the backend upload endpoints:
 *   - POST /api/upload/images   (one or more image files)
 *   - POST /api/upload/zip      (a single ZIP archive)
 *
 * Features:
 *   - Drag/drop images, a whole folder, or a ZIP
 *   - Browse files / Browse folder buttons
 *   - Collapsed file list by default once the queue exceeds COLLAPSE_THRESHOLD
 *   - Backend-offline banner & disabled Process button
 *   - Streams XHR upload progress into the existing queue UI
 *   - Surfaces success/error in a result card with the staging path
 *
 * Files queued from a ZIP and image files share a single queue. On submit we
 * send the images via /upload/images and each ZIP via /upload/zip, then merge
 * their results so the user sees one summary.
 */
import { appState } from "../../state/appState.js";
import { uploadStagedImages, uploadStagedZip } from "../../services/api.js";

const ACCEPTED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".tif", ".tiff"];
const COLLAPSE_THRESHOLD = 10;

function lower(name) {
  return String(name || "").toLowerCase();
}

function hasImageExtension(name) {
  const v = lower(name);
  return ACCEPTED_IMAGE_EXTENSIONS.some((ext) => v.endsWith(ext));
}

function isZipFile(file) {
  if (!file) return false;
  if (lower(file.name).endsWith(".zip")) return true;
  return file.type === "application/zip" || file.type === "application/x-zip-compressed";
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
    images: [],            // File[] of image files
    zips: [],              // File[] of ZIP archives
    cameraLocation: "Site 1",
    isUploading: false,
    progress: 0,           // 0..100, combined
    error: "",
    lastResult: null,      // merged backend payload
    listExpanded: false
  };

  let bound = false;

  function elements() {
    return {
      manualRoot: getById("upload-manual"),
      zone: getById("upload-zone"),
      fileInput: getById("upload-file-input"),
      folderInput: getById("upload-folder-input"),
      browseFilesBtn: getById("upload-browse-files-btn"),
      browseFolderBtn: getById("upload-browse-folder-btn"),
      list: getById("upload-queue-list"),
      meta: getById("upload-queue-meta"),
      summaryWrap: getById("upload-queue-summary"),
      summaryText: getById("upload-queue-summary-text"),
      toggleBtn: getById("upload-queue-toggle-btn"),
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

  function totalQueueCount() {
    return state.images.length + state.zips.length;
  }

  function totalQueueBytes() {
    const imgBytes = state.images.reduce((s, f) => s + (Number(f.size) || 0), 0);
    const zipBytes = state.zips.reduce((s, f) => s + (Number(f.size) || 0), 0);
    return imgBytes + zipBytes;
  }

  function isBackendConnected() {
    return Boolean(appState.backendHealth?.connected);
  }

  function statusLabel() {
    if (state.isUploading) return "Uploading";
    if (state.error) return "Error";
    if (state.lastResult) return "Uploaded";
    return "Ready";
  }

  function renderSummaryCards() {
    const els = elements();
    state.cameraLocation = readSelectedSite();
    const count = state.images.length;
    if (els.total) els.total.textContent = String(count);
    if (els.sizeStat) els.sizeStat.textContent = totalQueueCount() ? formatBytes(totalQueueBytes()) : "—";
    if (els.siteStat) els.siteStat.textContent = state.cameraLocation;
    if (els.statusStat) els.statusStat.textContent = statusLabel();
    if (els.meta) {
      const parts = [];
      if (state.images.length) parts.push(`${state.images.length} image(s)`);
      if (state.zips.length) parts.push(`${state.zips.length} ZIP file(s)`);
      if (state.isUploading) {
        els.meta.textContent = `Uploading… ${state.progress}%`;
      } else if (state.lastResult && !totalQueueCount()) {
        const c = state.lastResult.uploaded_count ?? 0;
        els.meta.textContent = `${c} file(s) saved · ${formatBytes(state.lastResult.total_bytes || 0)}`;
      } else if (parts.length) {
        els.meta.textContent = `${parts.join(" · ")} · ${formatBytes(totalQueueBytes())}`;
      } else {
        els.meta.textContent = "No files selected yet";
      }
    }
    if (els.barInfo) {
      if (state.isUploading) {
        els.barInfo.innerHTML = `Uploading <strong>${totalQueueCount()} file(s)</strong> to backend staging… ${state.progress}%`;
      } else if (state.lastResult && !totalQueueCount()) {
        const c = state.lastResult.uploaded_count ?? 0;
        const skipped = state.lastResult.skipped_count || 0;
        const skippedNote = skipped ? ` · skipped ${skipped} unsupported entry(ies)` : "";
        els.barInfo.innerHTML = `Processing complete: <strong>${c} image(s)</strong> staged${skippedNote}.`;
      } else if (state.error) {
        els.barInfo.textContent = state.error;
      } else if (totalQueueCount()) {
        const zipNote = state.zips.length ? ` · ZIP file detected` : "";
        els.barInfo.innerHTML = `<strong>${state.images.length} image(s)</strong> ready · ${formatBytes(totalQueueBytes())} · Site: ${state.cameraLocation}${zipNote}`;
      } else {
        els.barInfo.textContent = "Drop or browse wildlife camera images to begin.";
      }
    }
  }

  function renderQueue() {
    const els = elements();
    if (!els.list) return;
    els.list.innerHTML = "";

    const queue = [...state.zips, ...state.images];
    if (!queue.length) {
      const empty = document.createElement("div");
      empty.className = "upload-queue-empty";
      empty.textContent = state.lastResult
        ? "Queue cleared after upload. Add another batch to continue."
        : "No images selected yet. Drop wildlife camera images above or click Browse files.";
      els.list.appendChild(empty);
      if (els.summaryWrap) els.summaryWrap.hidden = true;
      return;
    }

    const shouldCollapse = !state.listExpanded && queue.length > COLLAPSE_THRESHOLD;
    if (els.summaryWrap) {
      // Show the "X images selected / Show all" header any time we have files.
      const totalImg = state.images.length;
      const totalZip = state.zips.length;
      const summaryParts = [];
      if (totalImg) summaryParts.push(`${totalImg} image${totalImg === 1 ? "" : "s"} ready`);
      if (totalZip) summaryParts.push(`${totalZip} ZIP file${totalZip === 1 ? "" : "s"} detected`);
      if (els.summaryText) els.summaryText.textContent = summaryParts.join(" · ");
      els.summaryWrap.hidden = false;
      if (els.toggleBtn) {
        if (queue.length > COLLAPSE_THRESHOLD) {
          els.toggleBtn.hidden = false;
          els.toggleBtn.textContent = state.listExpanded ? "Hide file list" : "Show all files";
        } else {
          // For small queues we still expand by default; hide the toggle button.
          els.toggleBtn.hidden = true;
        }
      }
    }

    if (shouldCollapse) {
      // Render a single compact summary row instead of every file.
      const compact = document.createElement("div");
      compact.className = "upload-queue-collapsed";
      compact.textContent = `File list collapsed for ${queue.length} file(s). Click "Show all files" to inspect.`;
      els.list.appendChild(compact);
      return;
    }

    const progressClass = state.isUploading ? "active" : state.lastResult ? "done" : "";
    const fillWidth = state.isUploading ? state.progress : state.lastResult ? 100 : 0;
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

    queue.forEach((file) => {
      const row = document.createElement("div");
      row.className = "upload-queue-item";
      const isZip = isZipFile(file);
      row.innerHTML = `
        <div class="queue-file-icon">
          ${isZip
            ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#3182CE" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8v13H3V8"/><path d="M1 3h22v5H1z"/><path d="M10 12h4"/></svg>`
            : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#3182CE" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`}
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
      row.querySelector(".queue-file-name").textContent = file.name;
      row.querySelector(".queue-file-meta").textContent = `${isZip ? "ZIP archive" : "Image"} · ${formatBytes(file.size)} · ${state.cameraLocation}`;
      row.querySelector(".queue-location-tag").textContent = state.cameraLocation;
      row.querySelector(".queue-size-text").textContent = formatBytes(file.size);
      els.list.appendChild(row);
    });
  }

  function renderControls() {
    const els = elements();
    const backendDown = !isBackendConnected();
    if (els.backendBanner) {
      els.backendBanner.hidden = !backendDown;
    }
    if (els.startBtn) {
      els.startBtn.disabled = state.isUploading || !totalQueueCount() || backendDown;
    }
    if (els.clearBtn) {
      els.clearBtn.disabled = state.isUploading
        || (!totalQueueCount() && !state.lastResult && !state.error);
    }
  }

  function renderResult() {
    const els = elements();
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
        const skippedNote = skipped ? ` Skipped ${skipped} unsupported entry(ies).` : "";
        els.resultDetails.textContent =
          `${formatBytes(totalBytesValue)} written to ${stagingDir}.${skippedNote}`
          + ` Open the Run Model page to process the staged images. Results will be exported as a CSV.`;
      }
      return;
    }
    els.result.hidden = true;
  }

  function render() {
    renderSummaryCards();
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

    const newImages = [];
    const newZips = [];
    let rejected = 0;
    incoming.forEach((file) => {
      if (isZipFile(file)) newZips.push(file);
      else if (isImageFile(file)) newImages.push(file);
      else rejected += 1;
    });

    if (!newImages.length && !newZips.length) {
      app.showToast("No supported files found (JPG, PNG, TIFF, ZIP).", "warn");
      return;
    }

    const imageMap = new Map(state.images.map((file) => [dedupeKey(file), file]));
    newImages.forEach((file) => {
      const key = dedupeKey(file);
      if (!imageMap.has(key)) imageMap.set(key, file);
    });
    state.images = Array.from(imageMap.values());

    const zipMap = new Map(state.zips.map((file) => [dedupeKey(file), file]));
    newZips.forEach((file) => {
      const key = dedupeKey(file);
      if (!zipMap.has(key)) zipMap.set(key, file);
    });
    state.zips = Array.from(zipMap.values());

    state.error = "";
    state.lastResult = null;
    state.progress = 0;
    // Re-collapse the list when a brand new batch is added so we don't dump
    // hundreds of rows into the page automatically.
    state.listExpanded = false;

    if (rejected > 0) {
      app.showToast(`Skipped ${rejected} unsupported file(s).`, "warn");
    }
    render();
  }

  function clearFiles() {
    state.images = [];
    state.zips = [];
    state.error = "";
    state.lastResult = null;
    state.progress = 0;
    state.listExpanded = false;
    render();
  }

  function mergeResults(...results) {
    const merged = {
      uploaded_count: 0,
      skipped_count: 0,
      total_bytes: 0,
      staging_dir: "",
      files: [],
      skipped: []
    };
    results.forEach((r) => {
      if (!r) return;
      merged.uploaded_count += Number(r.uploaded_count || 0);
      merged.skipped_count += Number(r.skipped_count || (r.skipped?.length ?? 0));
      merged.total_bytes += Number(r.total_bytes || 0);
      if (r.staging_dir && !merged.staging_dir) merged.staging_dir = r.staging_dir;
      if (Array.isArray(r.files)) merged.files = merged.files.concat(r.files);
      if (Array.isArray(r.skipped)) merged.skipped = merged.skipped.concat(r.skipped);
    });
    return merged;
  }

  async function startUpload() {
    if (state.isUploading || !totalQueueCount()) return;
    if (!isBackendConnected()) {
      app.showToast("Backend is not connected. Please start the backend and try again.", "warn");
      return;
    }
    state.isUploading = true;
    state.progress = 0;
    state.error = "";
    state.lastResult = null;
    render();

    // Each "step" gets an equal slice of overall progress so that mixing
    // images + multiple ZIPs still lands on a clean 100% at the end.
    const totalSteps = (state.images.length ? 1 : 0) + state.zips.length;
    let stepIndex = 0;

    function reportStepProgress(percent) {
      const safe = Math.max(0, Math.min(100, Number(percent) || 0));
      const stepShare = totalSteps > 0 ? 100 / totalSteps : 100;
      const overall = Math.round(stepIndex * stepShare + (safe / 100) * stepShare);
      state.progress = Math.max(0, Math.min(100, overall));
      renderSummaryCards();
      renderQueue();
    }

    const partials = [];
    try {
      if (state.images.length) {
        const result = await uploadStagedImages(state.images, {
          cameraLocation: state.cameraLocation,
          onProgress: ({ percent }) => reportStepProgress(percent)
        });
        partials.push(result);
        stepIndex += 1;
      }
      // ZIPs are uploaded one at a time so progress stays meaningful and any
      // single failure surfaces clearly with the archive name.
      for (const zipFile of state.zips) {
        const result = await uploadStagedZip(zipFile, {
          cameraLocation: state.cameraLocation,
          onProgress: ({ percent }) => reportStepProgress(percent)
        });
        partials.push(result);
        stepIndex += 1;
      }

      const merged = mergeResults(...partials);
      state.lastResult = merged;
      state.progress = 100;
      app.showToast(`Upload complete · ${merged.uploaded_count} image(s) saved`, "success");
      // Empty the queue but keep the result card around for confirmation.
      state.images = [];
      state.zips = [];
      state.listExpanded = false;
    } catch (error) {
      const message = error?.message || "Upload failed";
      state.error = message;
      app.showToast(message, "warn");
    } finally {
      state.isUploading = false;
      render();
    }
  }

  // ── DOM event handlers ───────────────────────────────────────────────
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
    if (event.target.closest("#upload-browse-files-btn")) return;
    if (event.target.closest("#upload-browse-folder-btn")) return;
    elements().fileInput?.click();
  }
  function handleZoneKeydown(event) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      elements().fileInput?.click();
    }
  }
  function handleBrowseFilesClick(event) {
    event.preventDefault();
    event.stopPropagation();
    elements().fileInput?.click();
  }
  function handleBrowseFolderClick(event) {
    event.preventDefault();
    event.stopPropagation();
    elements().folderInput?.click();
  }
  function handleFileInputChange(event) {
    addFiles(event.target?.files);
    if (event.target) event.target.value = "";
  }
  function handleSiteChange() {
    state.cameraLocation = readSelectedSite();
    render();
  }
  function handleToggleList() {
    state.listExpanded = !state.listExpanded;
    renderQueue();
  }

  function bindEvents() {
    const els = elements();
    if (bound || !els.zone || !els.fileInput) return false;
    els.zone.addEventListener("dragover", handleZoneDragOver);
    els.zone.addEventListener("dragleave", handleZoneDragLeave);
    els.zone.addEventListener("drop", handleZoneDrop);
    els.zone.addEventListener("click", handleZoneClick);
    els.zone.addEventListener("keydown", handleZoneKeydown);
    els.fileInput.addEventListener("change", handleFileInputChange);
    els.folderInput?.addEventListener("change", handleFileInputChange);
    els.browseFilesBtn?.addEventListener("click", handleBrowseFilesClick);
    els.browseFolderBtn?.addEventListener("click", handleBrowseFolderClick);
    els.startBtn?.addEventListener("click", () => { void startUpload(); });
    els.clearBtn?.addEventListener("click", clearFiles);
    els.toggleBtn?.addEventListener("click", handleToggleList);
    document.querySelectorAll("#upload-manual .loc-select-card").forEach((card) => {
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
