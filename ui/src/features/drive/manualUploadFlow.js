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
import { normalizeCameraSiteName } from "./cameraSiteName.js";

const ACCEPTED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".tif", ".tiff"];
const COLLAPSE_THRESHOLD = 10;
const QUEUE_BUTTON_ICON = `<span class="btn-icon btn-icon-upload" style="margin-right:5px"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg></span>`;
let nextBatchId = 1;

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

function detectTopLevelFolder(files) {
  // For folder picks (and folder drag-drop in modern browsers), each File has a
  // webkitRelativePath like "MyFolder/sub/IMG_0001.JPG". The top-level folder
  // is the first path segment. If every file shares the same top-level folder
  // we use that; otherwise detection is unavailable.
  const tops = new Set();
  for (const f of files) {
    const rel = String(f?.webkitRelativePath || "");
    if (rel.includes("/")) {
      tops.add(rel.split("/", 1)[0]);
      if (tops.size > 1) return "";
    }
  }
  return tops.size === 1 ? Array.from(tops)[0] : "";
}

function getTopLevelFolder(file) {
  const rel = String(file?.webkitRelativePath || "");
  return rel.includes("/") ? rel.split("/", 1)[0] : "";
}

function zipStem(zipFile) {
  const name = String(zipFile?.name || "");
  return name.replace(/\.zip$/i, "");
}

/**
 * Derive a likely camera-site name from a filename stem.
 * Wildlife camera filenames typically follow patterns like:
 *   "SITE1_0001.JPG"               → "SITE1"
 *   "Quail-Hill_IMG_0042.JPG"      → "Quail-Hill"
 *   "BommerCanyon-2024-10-09.JPG"  → "BommerCanyon"
 *   "IMG_0001.JPG"                 → ""        (just a generic camera prefix)
 *   "DSC00123.JPG"                 → ""        (Sony camera default)
 * The heuristic: take everything before the first "_DDDD" / "_IMG" / "-DDDD"
 * segment. Reject pure-digit and well-known generic camera prefixes.
 */
const FILENAME_GENERIC_PREFIXES = new Set([
  "img", "image", "dsc", "dscn", "p", "pic", "picture",
  "cam", "camera", "photo", "shot"
]);

function detectFromFilename(fileName) {
  const stem = String(fileName || "")
    .replace(/\.[A-Za-z0-9]+$/, "");  // strip extension
  if (!stem) return "";

  // Cut at the first delimiter (`_` or `-`) followed by digits, or at the
  // first run of 3+ digits in the stem.
  const match = stem.match(/^(.*?)(?:[ _-]?\d{3,})/);
  const candidate = (match ? match[1] : stem).replace(/[ _-]+$/g, "");

  if (!candidate) return "";
  if (candidate.length < 2) return "";
  if (/^\d+$/.test(candidate)) return "";
  if (FILENAME_GENERIC_PREFIXES.has(candidate.toLowerCase())) return "";
  return candidate;
}

function detectFromFilenames(files) {
  // Look for a single shared prefix across the queue. If every file maps to
  // the same non-empty candidate, use it; otherwise give up.
  const candidates = new Set();
  for (const f of files) {
    const c = detectFromFilename(f?.name);
    if (!c) continue;
    candidates.add(c);
    if (candidates.size > 1) return "";
  }
  return candidates.size === 1 ? Array.from(candidates)[0] : "";
}

function buildFallbackSiteName() {
  // Generates a unique, sortable name so two no-context uploads in the same
  // session don't collide on the backend.
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return (
    "Uploaded_Site_"
    + now.getFullYear()
    + pad(now.getMonth() + 1)
    + pad(now.getDate())
    + "_"
    + pad(now.getHours())
    + pad(now.getMinutes())
    + pad(now.getSeconds())
  );
}

async function countZipImageEntries(zipFile) {
  try {
    const buffer = await zipFile.arrayBuffer();
    const view = new DataView(buffer);
    const maxSearch = Math.max(0, buffer.byteLength - 65557);
    let eocdOffset = -1;
    for (let i = buffer.byteLength - 22; i >= maxSearch; i -= 1) {
      if (view.getUint32(i, true) === 0x06054b50) {
        eocdOffset = i;
        break;
      }
    }
    if (eocdOffset < 0) return null;
    const entryCount = view.getUint16(eocdOffset + 10, true);
    let cursor = view.getUint32(eocdOffset + 16, true);
    let imageCount = 0;
    const decoder = new TextDecoder();
    for (let i = 0; i < entryCount && cursor + 46 <= buffer.byteLength; i += 1) {
      if (view.getUint32(cursor, true) !== 0x02014b50) break;
      const nameLength = view.getUint16(cursor + 28, true);
      const extraLength = view.getUint16(cursor + 30, true);
      const commentLength = view.getUint16(cursor + 32, true);
      const nameStart = cursor + 46;
      const nameEnd = nameStart + nameLength;
      if (nameEnd > buffer.byteLength) break;
      const name = decoder.decode(new Uint8Array(buffer, nameStart, nameLength));
      if (!name.endsWith("/") && hasImageExtension(name)) imageCount += 1;
      cursor = nameEnd + extraLength + commentLength;
    }
    return imageCount;
  } catch (error) {
    return null;
  }
}

function createBatch({ type, files, sourceName, autoDetectedSite, imageCount = 0, imageCountPending = false }) {
  const detected = normalizeCameraSiteName(autoDetectedSite);
  return {
    id: `batch-${nextBatchId++}`,
    type,
    files,
    sourceName: sourceName || files[0]?.name || "Upload",
    autoDetectedSite: detected,
    siteOverride: "",
    cameraLocation: detected,
    imageCount,
    imageCountPending,
    progress: 0,
    status: "pending",
    error: "",
    result: null
  };
}

function normalizeBatchSite(batch) {
  const override = normalizeCameraSiteName(batch?.siteOverride);
  const detected = normalizeCameraSiteName(batch?.autoDetectedSite);
  batch.cameraLocation = override || detected || "";
  return batch.cameraLocation;
}

function batchSize(batch) {
  return (batch?.files || []).reduce((sum, file) => sum + (Number(file.size) || 0), 0);
}

function batchTypeLabel(batch) {
  if (batch?.type === "zip") return "ZIP";
  if (batch?.type === "folder") return "Folder";
  return "Files";
}

function dedupeKey(file) {
  return `${file.name}|${file.size}|${file.lastModified || 0}`;
}

function existingBatchKey(batch) {
  return `${batch.type}|${batch.sourceName}|${batch.files.map(dedupeKey).join(",")}`;
}

function buildBatchesFromFiles(files) {
  const batches = [];
  const folderGroups = new Map();
  const looseGroups = new Map();

  files.forEach((file) => {
    if (isZipFile(file)) {
      batches.push(createBatch({
        type: "zip",
        files: [file],
        sourceName: file.name,
        autoDetectedSite: zipStem(file),
        imageCount: 0,
        imageCountPending: true
      }));
      return;
    }

    if (!isImageFile(file)) return;

    const topFolder = getTopLevelFolder(file);
    if (topFolder) {
      if (!folderGroups.has(topFolder)) folderGroups.set(topFolder, []);
      folderGroups.get(topFolder).push(file);
      return;
    }

    const detected = normalizeCameraSiteName(detectFromFilename(file.name)) || "Loose files";
    if (!looseGroups.has(detected)) looseGroups.set(detected, []);
    looseGroups.get(detected).push(file);
  });

  folderGroups.forEach((groupFiles, folderName) => {
    batches.push(createBatch({
      type: "folder",
      files: groupFiles,
      sourceName: folderName,
      autoDetectedSite: folderName,
      imageCount: groupFiles.length
    }));
  });

  looseGroups.forEach((groupFiles, detectedName) => {
    const site = detectedName === "Loose files" && groupFiles.length > 1
      ? detectFromFilenames(groupFiles)
      : detectedName;
    batches.push(createBatch({
      type: "files",
      files: groupFiles,
      sourceName: site && site !== "Loose files" ? site : `${groupFiles.length} loose file${groupFiles.length === 1 ? "" : "s"}`,
      autoDetectedSite: site === "Loose files" ? "" : site,
      imageCount: groupFiles.length
    }));
  });

  return batches;
}

async function hydrateZipCounts(batches) {
  await Promise.all(batches.filter((batch) => batch.type === "zip").map(async (batch) => {
    const count = await countZipImageEntries(batch.files[0]);
    batch.imageCount = Number.isFinite(count) ? count : 0;
    batch.imageCountPending = false;
  }));
}

export function createManualUploadFlow(app) {
  const state = {
    batches: [],           // Upload batch objects; each has its own camera site.
    selectedBatchId: "",
    isUploading: false,
    cancelRequested: false,
    stopped: false,
    progress: 0,           // 0..100, combined
    error: "",
    lastResult: null,      // merged backend payload
    listExpanded: false,
    _uploadAbortController: null
  };

  let bound = false;

  function elements() {
    return {
      manualRoot: getById("upload-manual"),
      zone: getById("upload-zone"),
      fileInput: getById("upload-file-input"),
      folderInput: getById("upload-folder-input"),
      browseFilesBtn: getById("upload-browse-files-btn"),
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
      stopBtn: getById("upload-stop-btn"),
      result: getById("upload-result-card"),
      resultMessage: getById("upload-result-message"),
      resultDetails: getById("upload-result-details"),
      backendBanner: getById("upload-backend-banner"),
      siteAutoCard: getById("upload-site-auto-card"),
      siteCreateCard: getById("upload-site-create-card"),
      siteHelpWraps: document.querySelectorAll(".upload-site-help-wrap"),
      siteHelpButtons: document.querySelectorAll(".upload-site-help"),
      siteDetected: getById("upload-site-detected"),
      siteCustomValue: getById("upload-site-custom-value"),
      siteInput: getById("upload-site-input"),
      siteApplyBtn: getById("upload-site-apply-btn"),
      siteHelperPath: getById("upload-site-helper-path"),
      siteModal: getById("upload-site-modal"),
      siteModalInput: getById("upload-site-modal-input"),
      siteModalCancel: getById("upload-site-modal-cancel"),
      siteModalSave: getById("upload-site-modal-save"),
      summarySite: getById("upload-summary-site"),
      summaryFiles: getById("upload-summary-files"),
      summarySize: getById("upload-summary-size"),
      summaryType: getById("upload-summary-type"),
      summaryStaging: getById("upload-summary-staging"),
      summaryLastStatus: getById("upload-summary-last-status"),
      importSummaryUploads: getById("upload-import-summary-uploads"),
      importSummarySites: getById("upload-import-summary-sites"),
      importSummaryImages: getById("upload-import-summary-images"),
      importSummaryTypes: getById("upload-import-summary-types"),
      runtimeWarning: getById("upload-runtime-warning")
    };
  }

  function selectedBatch() {
    return state.batches.find((batch) => batch.id === state.selectedBatchId) || state.batches[0] || null;
  }

  function refreshSiteDetection() {
    state.batches.forEach(normalizeBatchSite);
  }

  function totalQueueCount() {
    return state.batches.length;
  }

  function totalQueueBytes() {
    return state.batches.reduce((sum, batch) => sum + batchSize(batch), 0);
  }

  function totalKnownImages() {
    return state.batches.reduce((sum, batch) => sum + (Number(batch.imageCount) || 0), 0);
  }

  function hasPendingZipCounts() {
    return state.batches.some((batch) => batch.imageCountPending);
  }

  function totalImageLabel() {
    const known = totalKnownImages();
    return hasPendingZipCounts() ? `${known}+` : String(known);
  }

  function detectedSiteCount() {
    return new Set(state.batches.map((batch) => normalizeCameraSiteName(batch.cameraLocation)).filter(Boolean)).size;
  }

  function uploadTypeLabel() {
    const types = Array.from(new Set(state.batches.map(batchTypeLabel)));
    return types.length ? types.join(" / ") : "—";
  }

  function stagingLocationLabel() {
    const sites = Array.from(new Set(state.batches.map((batch) => normalizeBatchSite(batch)).filter(Boolean)));
    if (!sites.length) return "data/staging/<camera_site>";
    if (sites.length === 1) return `data/staging/${sites[0]}`;
    return `${sites.length} staging folders`;
  }

  function isBackendConnected() {
    return Boolean(appState.backendHealth?.connected);
  }

  function statusLabel() {
    if (state.isUploading) return "Uploading";
    if (state.stopped) return "Stopped";
    if (state.error) return "Error";
    if (state.lastResult) return "Uploaded";
    return "Ready";
  }

  function renderSummaryCards() {
    const els = elements();
    refreshSiteDetection();
    if (els.total) els.total.textContent = totalImageLabel();
    if (els.sizeStat) els.sizeStat.textContent = totalQueueCount() ? formatBytes(totalQueueBytes()) : "—";
    // Mirror Drive mode's top strip: show the actual camera-site name when
    // there's exactly one, "Multiple" when batches span more than one site,
    // and "—" before anything is queued.
    if (els.siteStat) {
      const uniqueSites = Array.from(
        new Set(
          state.batches
            .map((batch) => normalizeCameraSiteName(batch.cameraLocation))
            .filter(Boolean)
        )
      );
      els.siteStat.textContent = uniqueSites.length === 0
        ? "—"
        : uniqueSites.length === 1
          ? uniqueSites[0]
          : "Multiple";
    }
    if (els.statusStat) els.statusStat.textContent = statusLabel();
    if (els.meta) {
      const parts = [];
      if (state.batches.length) parts.push(`${state.batches.length} upload${state.batches.length === 1 ? "" : "s"}`);
      if (totalKnownImages()) parts.push(`${totalImageLabel()} image(s)`);
      if (state.isUploading) {
        els.meta.textContent = `Uploading… ${state.progress}%`;
      } else if (state.stopped) {
        els.meta.textContent = "Stopped. Resume when ready.";
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
        els.barInfo.innerHTML = `Queueing <strong>${totalQueueCount()} upload${totalQueueCount() === 1 ? "" : "s"}</strong> for processing… ${state.progress}%`;
      } else if (state.stopped) {
        els.barInfo.textContent = "Stopped. Resume when ready.";
      } else if (state.lastResult && !totalQueueCount()) {
        const c = state.lastResult.uploaded_count ?? 0;
        const skipped = state.lastResult.skipped_count || 0;
        const skippedNote = skipped ? ` · skipped ${skipped} unsupported entry(ies)` : "";
        els.barInfo.innerHTML = `Queue complete: <strong>${c} image(s)</strong> staged${skippedNote}.`;
      } else if (state.error) {
        els.barInfo.textContent = state.error;
      } else if (totalQueueCount()) {
        els.barInfo.innerHTML = `<strong>${totalQueueCount()} upload${totalQueueCount() === 1 ? "" : "s"}</strong> ready · ${totalImageLabel()} image(s) · ${uploadTypeLabel()}`;
      } else {
        els.barInfo.textContent = "Drop or browse wildlife camera images to begin.";
      }
    }
    if (els.importSummaryUploads) els.importSummaryUploads.textContent = String(state.batches.length);
    if (els.importSummarySites) els.importSummarySites.textContent = String(detectedSiteCount());
    if (els.importSummaryImages) els.importSummaryImages.textContent = totalImageLabel();
    if (els.importSummaryTypes) els.importSummaryTypes.textContent = uploadTypeLabel();
  }

  function renderQueue() {
    const els = elements();
    if (!els.list) return;
    els.list.innerHTML = "";

    const queue = state.batches;
    if (!queue.length) {
      const empty = document.createElement("div");
      empty.className = "upload-queue-empty";
      empty.textContent = state.lastResult
        ? "Queue cleared after upload. Add another batch to continue."
        : "No uploads selected yet. Drop wildlife camera images, folders, or ZIPs above.";
      els.list.appendChild(empty);
      if (els.summaryWrap) els.summaryWrap.hidden = true;
      return;
    }

    const shouldCollapse = !state.listExpanded && queue.length > COLLAPSE_THRESHOLD;
    if (els.summaryWrap) {
      // Show the "X images selected / Show all" header any time we have files.
      const summaryParts = [];
      summaryParts.push(`${queue.length} upload${queue.length === 1 ? "" : "s"} detected`);
      summaryParts.push(`${totalImageLabel()} image${totalKnownImages() === 1 && !hasPendingZipCounts() ? "" : "s"}`);
      if (uploadTypeLabel() !== "—") summaryParts.push(uploadTypeLabel());
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
      compact.textContent = `Queue collapsed for ${queue.length} upload${queue.length === 1 ? "" : "s"}. Click "Show all" to inspect.`;
      els.list.appendChild(compact);
      return;
    }

    queue.forEach((batch) => {
      normalizeBatchSite(batch);
      const isSelected = batch.id === state.selectedBatchId;
      const progressClass = batch.status === "uploading" ? "active" : batch.status === "uploaded" ? "done" : "";
      const fillWidth = batch.status === "uploading" ? batch.progress : batch.status === "uploaded" ? 100 : 0;
      const pillClass = batch.status === "uploaded"
        ? "pill-green"
        : batch.status === "uploading"
          ? "pill-yellow"
          : batch.status === "error"
            ? "pill-red"
            : "pill-slate";
      const pillText = batch.status === "uploaded"
        ? "✓ Queued"
        : batch.status === "uploading"
          ? "Queueing…"
          : batch.status === "error"
            ? "Failed"
            : "Pending";
      const row = document.createElement("div");
      row.className = `upload-queue-item upload-batch-item${isSelected ? " selected" : ""}`;
      row.dataset.batchId = batch.id;
      const isZip = batch.type === "zip";
      const imageCountLabel = batch.imageCountPending ? "Counting…" : `${batch.imageCount} image${batch.imageCount === 1 ? "" : "s"}`;
      // Per-row Camera Site input was removed — the side panel + Create
      // camera site modal is the single naming flow now. Row layout is
      // icon · name+meta · site tag · size · progress · status+remove.
      row.innerHTML = `
        <div class="queue-file-icon">
          ${isZip
            ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#3182CE" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8v13H3V8"/><path d="M1 3h22v5H1z"/><path d="M10 12h4"/></svg>`
            : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#3182CE" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`}
        </div>
        <div class="queue-batch-main">
          <div class="queue-file-name"></div>
          <div class="queue-file-meta"></div>
        </div>
        <span class="queue-location-tag"></span>
        <span class="queue-size-text"></span>
        <div class="queue-prog-wrap">
          <div class="queue-prog-bar"><div class="queue-prog-fill ${progressClass}" style="width:${fillWidth}%"></div></div>
          <div class="queue-prog-pct">${fillWidth}%</div>
        </div>
        <div class="queue-batch-actions">
          <span class="status-pill ${pillClass}">${pillText}</span>
          <button type="button" class="queue-remove-btn" data-batch-id="${batch.id}">Remove</button>
        </div>
      `;
      row.querySelector(".queue-file-name").textContent = batch.sourceName;
      row.querySelector(".queue-file-meta").textContent = `${batchTypeLabel(batch)} · ${imageCountLabel}`;
      row.querySelector(".queue-location-tag").textContent = batch.cameraLocation || "No site";
      row.querySelector(".queue-remove-btn").disabled = state.isUploading;
      row.querySelector(".queue-size-text").textContent = formatBytes(batchSize(batch));
      els.list.appendChild(row);
    });
  }

  function renderSitePanel() {
    const els = elements();
    const batch = selectedBatch();
    const usingCustom = Boolean(normalizeCameraSiteName(batch?.siteOverride));
    if (els.siteDetected) {
      if (batch?.autoDetectedSite) {
        els.siteDetected.textContent = batch.autoDetectedSite;
        els.siteDetected.classList.remove("muted");
      } else {
        els.siteDetected.textContent = batch ? "Auto-detect unavailable" : "Select a queue item";
        els.siteDetected.classList.add("muted");
      }
    }
    if (els.siteCustomValue) {
      if (usingCustom && batch?.cameraLocation) {
        els.siteCustomValue.textContent = batch.cameraLocation;
        els.siteCustomValue.classList.remove("muted");
      } else {
        els.siteCustomValue.textContent = "No site selected";
        els.siteCustomValue.classList.add("muted");
      }
    }
    if (els.siteAutoCard) {
      els.siteAutoCard.classList.toggle("selected", !usingCustom);
      els.siteAutoCard.setAttribute("aria-pressed", !usingCustom ? "true" : "false");
      els.siteAutoCard.disabled = !batch;
    }
    if (els.siteCreateCard) {
      els.siteCreateCard.classList.toggle("selected", usingCustom);
      els.siteCreateCard.setAttribute("aria-pressed", usingCustom ? "true" : "false");
      els.siteCreateCard.disabled = !batch;
    }
    if (els.siteInput && document.activeElement !== els.siteInput) {
      els.siteInput.value = batch?.siteOverride || "";
    }
    if (els.siteHelperPath) {
      const label = batch?.cameraLocation || "&lt;site&gt;";
      els.siteHelperPath.innerHTML = `data/staging/${label}/`;
    }
  }

  function renderUploadSummary() {
    const els = elements();
    const fileCount = totalQueueCount();
    if (els.summarySite) els.summarySite.textContent = detectedSiteCount() > 1 ? "Multiple" : selectedBatch()?.cameraLocation || "—";
    if (els.summaryFiles) els.summaryFiles.textContent = totalImageLabel();
    if (els.summarySize) els.summarySize.textContent = fileCount ? formatBytes(totalQueueBytes()) : "—";
    if (els.summaryType) els.summaryType.textContent = uploadTypeLabel();
    if (els.summaryStaging) els.summaryStaging.textContent = stagingLocationLabel();
    if (els.summaryLastStatus) els.summaryLastStatus.textContent = state.error || statusLabel();
    if (els.runtimeWarning) {
      els.runtimeWarning.hidden = !appState.backendHealth?.connected || Boolean(appState.backendHealth?.pipelineRuntimeReady);
    }
    renderProgressCard();
  }

  function renderProgressCard() {
    const set = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    };
    const fileCount = totalQueueCount();
    const totalImages = totalKnownImages();
    const status = statusLabel();              // Ready / Uploading / Uploaded / Error
    const tone = state.error
      ? "failed"
      : state.isUploading
        ? "active"
        : state.lastResult
          ? "done"
          : "idle";

    // Header pill
    const pill = document.getElementById("upload-progress-status");
    if (pill) {
      pill.className = `upload-progress-status-pill ${tone}`;
      pill.textContent = status;
    }

    // Source row (selected files / batches summary)
    const batch = selectedBatch();
    const sourceName = !fileCount
      ? (state.lastResult ? "Queue cleared after upload" : "No files selected")
      : fileCount === 1
        ? batch?.sourceName || "1 upload"
        : `${fileCount} uploads selected`;
    const sub = state.error
      ? state.error
      : state.isUploading
        ? `Uploading ${state.progress}%`
        : state.stopped
          ? "Stopped. Resume when ready."
        : state.lastResult
          ? `${state.lastResult.uploaded_count || 0} image(s) staged`
          : fileCount
            ? `${totalImages || totalImageLabel()} image(s)`
            : "Drop images, a folder, or a ZIP to begin.";
    set("upload-progress-source-name", sourceName);
    set("upload-progress-source-sub", sub);

    // Camera-site pill (consistent with Drive mode)
    const sitePill = document.getElementById("upload-progress-site-pill");
    if (sitePill) {
      const siteCount = detectedSiteCount();
      const label = siteCount > 1
        ? `${siteCount} sites`
        : (batch?.cameraLocation || "");
      if (label) {
        sitePill.textContent = label;
        sitePill.classList.remove("muted");
      } else {
        sitePill.textContent = "No site";
        sitePill.classList.add("muted");
      }
    }

    // Progress bar
    const done = state.lastResult
      ? (state.lastResult.uploaded_count || 0)
      : state.isUploading
        ? Math.round((state.progress / 100) * totalImages)
        : state.stopped
          ? state.batches
              .filter((batch) => batch.status === "uploaded")
              .reduce((sum, batch) => sum + (Number(batch.imageCount) || 0), 0)
        : 0;
    const percent = Math.max(0, Math.min(100, Math.round(state.progress || (state.lastResult ? 100 : 0))));
    const fill = document.getElementById("upload-progress-fill");
    if (fill) {
      fill.className = `upload-progress-bar-fill ${tone === "idle" ? "" : tone}`.trim();
      fill.style.width = `${percent}%`;
    }
    set("upload-progress-pct", `${percent}%`);
    set("upload-progress-done", String(done || (state.lastResult ? totalImages : 0)));
    set("upload-progress-total", state.lastResult
      ? String(state.lastResult.uploaded_count || totalImages || 0)
      : (hasPendingZipCounts() ? totalImageLabel() : String(totalImages || 0)));

    // Visible stats: Files · Size · Speed
    const sizeLabel = fileCount ? formatBytes(totalQueueBytes()) : "—";
    let ipsLabel = "—";
    if (state.isUploading && state._uploadStartedAt && done > 0) {
      const elapsed = Math.max(0.001, (Date.now() - state._uploadStartedAt) / 1000);
      const ips = done / elapsed;
      if (Number.isFinite(ips) && ips > 0) {
        ipsLabel = `${ips.toFixed(ips >= 10 ? 0 : 1)} img/s`;
      }
    } else if (state.lastResult && state._uploadStartedAt && state._uploadEndedAt) {
      const elapsed = Math.max(0.001, (state._uploadEndedAt - state._uploadStartedAt) / 1000);
      const total = state.lastResult.uploaded_count || 0;
      if (total > 0) {
        const ips = total / elapsed;
        if (Number.isFinite(ips) && ips > 0) {
          ipsLabel = `${ips.toFixed(ips >= 10 ? 0 : 1)} img/s`;
        }
      }
    }
    set("upload-progress-files", String(totalImages || fileCount || 0));
    set("upload-progress-size", sizeLabel);
    set("upload-progress-ips", ipsLabel);

    // Hidden legacy fields kept so any earlier code that still reads them
    // does not error out.
    set("upload-progress-status-text", state.error || status);
    set("upload-progress-batches", String(fileCount));
    set("upload-progress-type", uploadTypeLabel());
    const remaining = state.isUploading
      ? Math.max(0, totalImages - done)
      : state.stopped
        ? Math.max(0, totalImages - done)
        : (totalImages && !state.lastResult ? totalImages : 0);
    set("upload-progress-remaining", remaining ? String(remaining) : (state.lastResult ? "0" : "—"));
    set("upload-progress-updated",
      state.lastResult ? "Just now" : state.isUploading ? "Live" : (fileCount ? "Just now" : "—")
    );
  }

  function renderControls() {
    const els = elements();
    const backendDown = !isBackendConnected();
    if (els.backendBanner) {
      els.backendBanner.hidden = !backendDown;
    }
    // Block queueing until every batch has a camera site name.
    const missingSite = state.batches.some((batch) => !normalizeBatchSite(batch));
    const hasPending = state.batches.some((batch) => batch.status !== "uploaded");
    if (els.startBtn) {
      const startLabel = state.stopped ? "Resume" : "Queue for Processing";
      els.startBtn.hidden = state.isUploading;
      els.startBtn.disabled = state.isUploading || !totalQueueCount() || backendDown || missingSite || !hasPending;
      if (els.startBtn.dataset.uploadLabel !== startLabel) {
        els.startBtn.innerHTML = `${QUEUE_BUTTON_ICON}${startLabel}`;
        els.startBtn.dataset.uploadLabel = startLabel;
      }
      els.startBtn.title = missingSite && totalQueueCount()
        ? "Every upload needs a camera site name before queueing."
        : "";
    }
    if (els.clearBtn) {
      els.clearBtn.disabled = state.isUploading
        || (!totalQueueCount() && !state.lastResult && !state.error && !state.stopped);
    }
    // Stop button mirrors the Drive sync Stop: visible only while an upload
    // is in flight, hidden once idle / done / error. The click handler
    // (cancelManualUpload) reuses the existing pipeline cancel route.
    if (els.stopBtn) {
      els.stopBtn.hidden = !state.isUploading;
      els.stopBtn.disabled = !state.isUploading;
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
    if (state.stopped) {
      els.result.hidden = false;
      els.result.classList.remove("upload-result-success");
      els.result.classList.remove("upload-result-error");
      if (els.resultMessage) els.resultMessage.textContent = "Stopped. Resume when ready.";
      if (els.resultDetails) els.resultDetails.textContent = "Queued files stay in place until you resume or clear them.";
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
        els.resultMessage.textContent = `Queue complete · ${count} image(s) staged`;
      }
      if (els.resultDetails) {
        const skippedNote = skipped ? ` Skipped ${skipped} unsupported entry(ies).` : "";
        els.resultDetails.textContent =
          `${formatBytes(totalBytesValue)} written to ${stagingDir}.${skippedNote}`
          + ` Open Run Model when you are ready to process the staged images.`;
      }
      return;
    }
    els.result.hidden = true;
  }

  function render() {
    renderSummaryCards();
    renderQueue();
    renderSitePanel();
    renderUploadSummary();
    renderControls();
    renderResult();
  }

  async function addFiles(fileList) {
    if (!fileList || !fileList.length) return;
    const incoming = Array.from(fileList);
    const startingNewBatch = !totalQueueCount() || Boolean(state.lastResult);
    let rejected = 0;
    const supported = incoming.filter((file) => {
      const ok = isZipFile(file) || isImageFile(file);
      if (!ok) rejected += 1;
      return ok;
    });

    if (!supported.length) {
      app.showToast("No supported files found (JPG, PNG, TIFF, ZIP).", "warn");
      return;
    }

    const newBatches = buildBatchesFromFiles(supported);
    const existingKeys = new Set(startingNewBatch ? [] : state.batches.map(existingBatchKey));
    const uniqueBatches = newBatches.filter((batch) => {
      const key = existingBatchKey(batch);
      if (existingKeys.has(key)) return false;
      existingKeys.add(key);
      return true;
    });
    if (!uniqueBatches.length) {
      app.showToast("Those uploads are already in the queue.", "warn");
      return;
    }

    state.error = "";
    state.lastResult = null;
    state.stopped = false;
    state.cancelRequested = false;
    state.progress = 0;
    if (startingNewBatch) state.batches = [];
    state.batches = state.batches.concat(uniqueBatches);
    if (!state.selectedBatchId || !state.batches.some((batch) => batch.id === state.selectedBatchId)) {
      state.selectedBatchId = uniqueBatches[0]?.id || state.batches[0]?.id || "";
    }
    // Re-collapse the list when a brand new batch is added so we don't dump
    // hundreds of rows into the page automatically.
    state.listExpanded = false;

    refreshSiteDetection();
    const detectedCount = uniqueBatches.filter((batch) => batch.cameraLocation).length;
    app.showToast(`${uniqueBatches.length} upload${uniqueBatches.length === 1 ? "" : "s"} added · ${detectedCount} camera site${detectedCount === 1 ? "" : "s"} detected`, detectedCount ? "success" : "warn");

    if (rejected > 0) {
      app.showToast(`Skipped ${rejected} unsupported file(s).`, "warn");
    }
    render();
    await hydrateZipCounts(uniqueBatches);
    render();
  }

  function clearFiles() {
    state.batches = [];
    state.selectedBatchId = "";
    state.error = "";
    state.lastResult = null;
    state.stopped = false;
    state.cancelRequested = false;
    state._uploadAbortController?.abort?.();
    state._uploadAbortController = null;
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
    const pendingBatches = state.batches.filter((batch) => batch.status !== "uploaded");
    const missingSite = pendingBatches.find((batch) => !normalizeBatchSite(batch));
    if (missingSite) {
      state.selectedBatchId = missingSite.id;
      render();
      app.showToast("Every upload needs a camera site before queueing.", "warn");
      return;
    }
    state.isUploading = true;
    state.cancelRequested = false;
    state.stopped = false;
    state.progress = 0;
    state.error = "";
    state.lastResult = null;
    state._uploadStartedAt = Date.now();
    state._uploadEndedAt = null;
    const uploadAbortController = new AbortController();
    state._uploadAbortController = uploadAbortController;
    render();

    // Each batch gets an equal slice of overall progress so unrelated
    // folders/ZIPs stay independent while still showing one compact total.
    const totalSteps = pendingBatches.length;
    let stepIndex = 0;

    function reportStepProgress(batch, percent) {
      if (state.cancelRequested) return;
      const safe = Math.max(0, Math.min(100, Number(percent) || 0));
      const stepShare = totalSteps > 0 ? 100 / totalSteps : 100;
      const overall = Math.round(stepIndex * stepShare + (safe / 100) * stepShare);
      state.progress = Math.max(0, Math.min(100, overall));
      batch.progress = safe;
      renderSummaryCards();
      renderQueue();
    }

    const partials = [];
    try {
      for (const batch of pendingBatches) {
        if (state.cancelRequested) break;
        batch.status = "uploading";
        batch.progress = 0;
        batch.error = "";
        renderQueue();
        const result = batch.type === "zip"
          ? await uploadStagedZip(batch.files[0], {
            cameraLocation: batch.cameraLocation,
            onProgress: ({ percent }) => reportStepProgress(batch, percent),
            signal: uploadAbortController.signal
          })
          : await uploadStagedImages(batch.files, {
            cameraLocation: batch.cameraLocation,
            onProgress: ({ percent }) => reportStepProgress(batch, percent),
            signal: uploadAbortController.signal
          });
        if (state.cancelRequested) {
          batch.status = "pending";
          batch.progress = 0;
          batch.error = "";
          state.stopped = true;
          break;
        }
        batch.status = "uploaded";
        batch.progress = 100;
        batch.result = result;
        partials.push(result);
        stepIndex += 1;
      }

      if (state.cancelRequested) {
        state.stopped = true;
        state.error = "";
        state.lastResult = null;
        return;
      }

      const merged = mergeResults(...partials);
      state.lastResult = merged;
      state.progress = 100;
      app.showToast(`Queue complete · ${merged.uploaded_count} image(s) staged`, "success");
    } catch (error) {
      const message = error?.message || "Upload failed";
      if (state.cancelRequested || message === "Upload cancelled.") {
        state.stopped = true;
        state.error = "";
        state.lastResult = null;
        const uploading = state.batches.find((batch) => batch.status === "uploading");
        if (uploading) {
          uploading.status = "pending";
          uploading.progress = 0;
          uploading.error = "";
        }
      } else {
        state.error = message;
        const uploading = state.batches.find((batch) => batch.status === "uploading");
        if (uploading) {
          uploading.status = "error";
          uploading.error = message;
        }
        app.showToast(message, "warn");
      }
    } finally {
      state.isUploading = false;
      state._uploadEndedAt = Date.now();
      if (state._uploadAbortController === uploadAbortController) {
        state._uploadAbortController = null;
      }
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
    void addFromDataTransfer(event.dataTransfer);
  }

  // Recursively walk an entries-style DataTransfer so dropping a *folder*
  // (not just loose files) actually picks up every image inside, including
  // nested subfolders. Falls back to a flat .files read on browsers that
  // don't expose webkitGetAsEntry / FileSystemEntry.
  async function addFromDataTransfer(dataTransfer) {
    if (!dataTransfer) return;
    const items = dataTransfer.items ? Array.from(dataTransfer.items) : [];
    const entries = items
      .map((item) => (typeof item.webkitGetAsEntry === "function" ? item.webkitGetAsEntry() : null))
      .filter(Boolean);

    if (!entries.length) {
      await addFiles(dataTransfer.files);
      return;
    }

    const collected = [];
    await Promise.all(entries.map((entry) => collectFilesFromEntry(entry, "", collected)));
    if (!collected.length) {
      await addFiles(dataTransfer.files);
      return;
    }
    await addFiles(collected);
  }

  function collectFilesFromEntry(entry, relativePath, out) {
    if (!entry) return Promise.resolve();
    if (entry.isFile) {
      return new Promise((resolve) => {
        entry.file(
          (file) => {
            // Keep webkitRelativePath-style hint so detectTopLevelFolder()
            // can still recognise folder-drop batches.
            try {
              const rel = relativePath ? `${relativePath}/${file.name}` : file.name;
              if (!file.webkitRelativePath) {
                Object.defineProperty(file, "webkitRelativePath", { value: rel, configurable: true });
              }
            } catch (error) { /* defineProperty on File can fail on some browsers; ignore */ }
            out.push(file);
            resolve();
          },
          () => resolve()
        );
      });
    }
    if (entry.isDirectory) {
      const reader = entry.createReader();
      const childRelative = relativePath ? `${relativePath}/${entry.name}` : entry.name;
      return new Promise((resolve) => {
        const readBatch = () => {
          reader.readEntries(async (batch) => {
            if (!batch.length) {
              resolve();
              return;
            }
            await Promise.all(batch.map((child) => collectFilesFromEntry(child, childRelative, out)));
            readBatch();
          }, () => resolve());
        };
        readBatch();
      });
    }
    return Promise.resolve();
  }
  function handleZoneClick(event) {
    if (event.target.closest("#upload-browse-files-btn")) return;
    const els = elements();
    if (event.shiftKey && els.folderInput) els.folderInput.click();
    else els.fileInput?.click();
  }
  function handleZoneKeydown(event) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      const els = elements();
      if (event.shiftKey && els.folderInput) els.folderInput.click();
      else els.fileInput?.click();
    }
  }
  function closeSiteHelpPopovers() {
    elements().siteHelpWraps?.forEach((wrap) => {
      wrap.classList.remove("open");
      wrap.querySelector(".upload-site-help")?.setAttribute("aria-expanded", "false");
    });
  }
  function toggleSiteHelpPopover(event) {
    event.preventDefault();
    event.stopPropagation();
    const wrap = event.currentTarget?.closest(".upload-site-help-wrap");
    const willOpen = !wrap?.classList.contains("open");
    closeSiteHelpPopovers();
    if (!wrap || !willOpen) return;
    wrap.classList.add("open");
    event.currentTarget.setAttribute("aria-expanded", "true");
  }
  function handleBrowseFilesClick(event) {
    event.preventDefault();
    event.stopPropagation();
    const els = elements();
    if (event.shiftKey && els.folderInput) els.folderInput.click();
    else els.fileInput?.click();
  }
  function handleFileInputChange(event) {
    void addFiles(event.target?.files);
    if (event.target) event.target.value = "";
  }
  function handleToggleList() {
    state.listExpanded = !state.listExpanded;
    renderQueue();
  }
  function handleSiteInputChange(event) {
    const batch = selectedBatch();
    if (!batch) return;
    batch.siteOverride = String(event.target?.value || "");
    normalizeBatchSite(batch);
    renderSummaryCards();
    renderSitePanel();
    renderControls();
  }
  function handleSiteInputKeydown(event) {
    if (event.key === "Enter") {
      event.preventDefault();
      applySiteOverride();
    }
  }
  function selectAutoSite() {
    const batch = selectedBatch();
    if (!batch) return;
    batch.siteOverride = "";
    normalizeBatchSite(batch);
    render();
  }
  function openSiteModal() {
    const els = elements();
    const batch = selectedBatch();
    if (!batch) return;
    if (!els.siteModal || !els.siteModalInput) return;
    els.siteModal.hidden = false;
    els.siteModalInput.value = batch.siteOverride || batch.cameraLocation || "";
    window.requestAnimationFrame(() => els.siteModalInput?.focus());
  }
  function closeSiteModal() {
    const els = elements();
    if (els.siteModal) els.siteModal.hidden = true;
  }
  function handleSiteModalKeydown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeSiteModal();
    }
    if (event.key === "Enter") {
      event.preventDefault();
      applySiteOverride();
    }
  }
  function applySiteOverride() {
    const els = elements();
    const batch = selectedBatch();
    if (!batch) return;
    const raw = String(els.siteModalInput?.value || els.siteInput?.value || "").trim();
    batch.siteOverride = raw;
    normalizeBatchSite(batch);
    if (batch.cameraLocation) {
      app.showToast(`Camera site set to: ${batch.cameraLocation}`, "success");
      closeSiteModal();
    } else {
      app.showToast("Enter a camera site name first.", "warn");
    }
    render();
  }

  function removeBatch(batchId) {
    state.batches = state.batches.filter((batch) => batch.id !== batchId);
    if (state.selectedBatchId === batchId) state.selectedBatchId = state.batches[0]?.id || "";
    state.error = "";
    state.lastResult = null;
    if (!state.batches.length) {
      state.stopped = false;
      state.cancelRequested = false;
    }
    render();
  }

  function handleQueueClick(event) {
    const removeBtn = event.target.closest(".queue-remove-btn");
    if (removeBtn) {
      event.preventDefault();
      removeBatch(removeBtn.dataset.batchId);
      return;
    }
    const tag = event.target.closest(".queue-location-tag");
    if (tag) {
      // Clicking the site pill inside a row is a shortcut to rename — open
      // the same modal the review strip uses, for that row's batch.
      event.preventDefault();
      const row = tag.closest(".upload-batch-item");
      const batchId = row?.dataset.batchId || "";
      if (batchId && state.batches.some((b) => b.id === batchId)) {
        state.selectedBatchId = batchId;
        openSiteModal();
        render();
      }
      return;
    }
    const row = event.target.closest(".upload-batch-item");
    if (!row) return;
    state.selectedBatchId = row.dataset.batchId || "";
    renderSitePanel();
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
    els.startBtn?.addEventListener("click", () => { void startUpload(); });
    els.clearBtn?.addEventListener("click", clearFiles);
    els.toggleBtn?.addEventListener("click", handleToggleList);
    els.list?.addEventListener("click", handleQueueClick);
    els.siteInput?.addEventListener("input", handleSiteInputChange);
    els.siteInput?.addEventListener("keydown", handleSiteInputKeydown);
    els.siteApplyBtn?.addEventListener("click", applySiteOverride);
    els.siteHelpButtons?.forEach((button) => button.addEventListener("click", toggleSiteHelpPopover));
    els.siteAutoCard?.addEventListener("click", selectAutoSite);
    els.siteCreateCard?.addEventListener("click", openSiteModal);
    els.siteModalCancel?.addEventListener("click", closeSiteModal);
    els.siteModalSave?.addEventListener("click", applySiteOverride);
    els.siteModalInput?.addEventListener("keydown", handleSiteModalKeydown);
    els.siteModal?.addEventListener("click", (event) => {
      if (event.target === els.siteModal) closeSiteModal();
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".upload-site-help-wrap")) closeSiteHelpPopovers();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeSiteHelpPopovers();
    });
    bound = true;
    return true;
  }

  function initialize() {
    if (!bindEvents()) return;
    refreshSiteDetection();
    render();
  }

  function refresh() {
    if (!bound) return;
    render();
  }

  // Stop a running manual upload. Cancels any in-flight pipeline run via
  // the existing /api/pipeline/cancel route, then flips local state so the
  // queue/UI returns to a clean idle state.
  async function cancelManualUpload() {
    if (!state.isUploading) return;
    state.cancelRequested = true;
    state.stopped = true;
    state.error = "";
    state._uploadAbortController?.abort?.();
    state.batches.forEach((batch) => {
      if (batch.status === "uploading") {
        batch.status = "pending";
        batch.progress = 0;
        batch.error = "";
      }
    });
    state.isUploading = false;
    render();
    try {
      if (typeof app.features?.pipeline?.cancelPipelineRun === "function") {
        await app.features.pipeline.cancelPipelineRun({ silentNoop: true });
      }
    } catch (error) {
      console.warn("Manual upload cancel failed:", error);
    }
    render();
    app.showToast?.("Upload stopped. Resume when ready.", "warn");
  }

  return { initialize, refresh, startUpload, clearFiles, cancelManualUpload };
}
