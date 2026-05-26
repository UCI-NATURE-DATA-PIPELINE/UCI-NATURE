/** Pipeline feature state helpers for run history and panel snapshots. */
import {
  escapeHtml,
  formatDecimal,
  formatDurationLabel,
  formatNumber,
  formatTimestampLabel
} from "../../utils/format.js";
import {
  getPipelineCurrentStepLabel,
  getPipelineMetrics,
  getPipelineOverallStatusLabel,
  getPipelineSourceMode
} from "../../utils/helpers.js";

const RUN_HISTORY_KEY = "uci_nature_run_history";
const MAX_HISTORY = 50;

const RUN_HISTORY_FILTER_KEY = "uci_nature_run_history_filter";

function loadDateRange() {
  try {
    const stored = localStorage.getItem(RUN_HISTORY_FILTER_KEY);
    if (!stored) return { from: "", to: "" };
    const parsed = JSON.parse(stored);
    return {
      from: typeof parsed.from === "string" ? parsed.from : "",
      to: typeof parsed.to === "string" ? parsed.to : ""
    };
  } catch (e) {
    return { from: "", to: "" };
  }
}

function saveDateRange(range) {
  try {
    if (range && (range.from || range.to)) {
      localStorage.setItem(RUN_HISTORY_FILTER_KEY, JSON.stringify(range));
    } else {
      localStorage.removeItem(RUN_HISTORY_FILTER_KEY);
    }
  } catch (e) {
    // ignore
  }
}

function matchesDateRange(run, range) {
  if (!range || (!range.from && !range.to)) return true;
  const runTimestamp = run.finished_at || run.started_at;
  if (!runTimestamp) return false;
  const runDate = String(runTimestamp).slice(0, 10);
  if (range.from && runDate < range.from) return false;
  if (range.to && runDate > range.to) return false;
  return true;
}

function loadStoredRuns() {
  try {
    const stored = localStorage.getItem(RUN_HISTORY_KEY);
    if (!stored) return [];
    const parsed = JSON.parse(stored);
    return Array.isArray(parsed) ? parsed : [];
  } catch (e) {
    return [];
  }
}

function saveStoredRuns(runs) {
  try {
    const trimmed = runs.slice(0, MAX_HISTORY);
    localStorage.setItem(RUN_HISTORY_KEY, JSON.stringify(trimmed));
  } catch (e) {
    console.warn("Failed to save run history", e);
  }
}

function snapshotRun(status) {
  // Capture a minimal serializable snapshot of a finished run.
  const metrics = getPipelineMetrics(status);
  return {
    run_id: String(status.run_id || ""),
    status: status?.status || "unknown",
    started_at: status?.started_at || null,
    finished_at: status?.finished_at || null,
    elapsed_seconds: status?.result?.elapsed_seconds || null,
    batch_size: status?.payload?.batch_size || null,
    manifest_rows: metrics.manifestRows || 0,
    processed_rows: metrics.processedRows || 0,
    review_items: metrics.reviewItems || 0,
    exported_rows: metrics.exportedRows || 0,
    failure_count: metrics.failureCount,
    throughput: metrics.throughput || null,
    notes: Array.isArray(status?.result?.notes) ? status.result.notes : []
  };
}

export function createPipelineState(app) {
  // Track which run_ids we've already recorded so we don't duplicate on every poll.
  const recordedRunIds = new Set(loadStoredRuns().map(r => r.run_id));

  function maybeRecordCompletedRun(status) {
    if (!status?.run_id) return;
    if (status.status !== "completed" && status.status !== "failed") return;
    if (recordedRunIds.has(String(status.run_id))) return;

    const snapshot = snapshotRun(status);
    const runs = loadStoredRuns();
    runs.unshift(snapshot);
    saveStoredRuns(runs);
    recordedRunIds.add(String(status.run_id));
  }

  function getPipelinePanelSnapshot(status) {
    const sourceMode = getPipelineSourceMode(status, app.state.uploadTab);
    const state = String(status?.status || "idle").toLowerCase();
    const currentStepKey = String(status?.progress?.step || status?.current_step || "").toLowerCase();
    const progressDetails = status?.progress?.details || {};
    const completedImageCount = Number(status?.result?.source?.image_count || 0);
    const discoveredCount = Number(app.state.driveSyncState.discovered_count || 0);
    const downloadedCount = Number(app.state.driveSyncState.downloaded_count || 0);
    const rawProcessedImages = Number(progressDetails?.processed_images);
    const rawTotalImages = Number(progressDetails?.total_images);
    const mlActive = state === "running" && currentStepKey.includes("run speciesnet");
    const totalImages = mlActive && Number.isFinite(rawTotalImages) && rawTotalImages >= 0 ? rawTotalImages : null;
    const processedImages = mlActive ? (Number.isFinite(rawProcessedImages) && rawProcessedImages >= 0 ? rawProcessedImages : 0) : null;
    const mlProgressPercent = mlActive && totalImages && totalImages > 0 ? Math.max(0, Math.min(100, Math.round((processedImages / totalImages) * 100))) : 0;

    let discovered = null;
    let downloaded = null;
    if (sourceMode === "drive") {
      discovered = discoveredCount || (completedImageCount > 0 ? completedImageCount : null);
      downloaded = downloadedCount || (status?.status === "completed" && completedImageCount > 0 ? completedImageCount : null);
    } else if (status?.status === "completed" && completedImageCount > 0) {
      discovered = completedImageCount;
    }

    return {
      overallStatus: getPipelineOverallStatusLabel(status),
      currentStep: getPipelineCurrentStepLabel(status),
      discovered,
      downloaded,
      currentFile: sourceMode === "drive" ? (app.state.driveSyncState.current_file || null) : null,
      logPath: status?.log_path || null,
      error: status?.error || (sourceMode === "drive" ? app.state.driveSyncState.error : null) || null,
      mlActive: mlActive && totalImages !== null,
      processedImages,
      totalImages,
      mlProgressPercent
    };
  }

  function renderHistoryRow(run, { isLive = false } = {}) {
    const statusClass = run.status === "completed" ? "pill-green" : run.status === "failed" ? "pill-red" : "pill-yellow";
    const statusLabel = run.status === "completed" ? "Success" : run.status === "failed" ? "Failed" : run.status === "running" ? "Running" : "Idle";
    const failureText = run.failure_count === null || run.failure_count === undefined ? "—" : formatNumber(run.failure_count);
    const durationText = run.status === "running" ? "In progress" : (run.elapsed_seconds ? formatDurationLabel(run.elapsed_seconds) : "—");
    const batchLabel = run.batch_size === "all" ? "All" : run.batch_size || "Unknown";
    const imageCountText = run.manifest_rows ? formatNumber(run.manifest_rows) : batchLabel === "All" ? "All staged" : batchLabel;
    const detailId = String(run.run_id).replace(/[^a-zA-Z0-9_-]/g, "");
    const notes = Array.isArray(run.notes) ? run.notes : [];

    return `
      <tr>
        <td><span class="batch-num">${escapeHtml(String(run.run_id))}</span>${isLive ? ` <span style="font-size:10px;color:var(--blue);font-weight:600;margin-left:4px">LIVE</span>` : ""}</td>
        <td>${escapeHtml(formatTimestampLabel(run.finished_at || run.started_at))}</td>
        <td>${escapeHtml(String(imageCountText))}</td>
        <td>${escapeHtml(durationText)}</td>
        <td><span class="status-pill ${statusClass}">${escapeHtml(statusLabel)}</span></td>
        <td><span class="${run.failure_count ? "failure-warn" : "failure-zero"}">${escapeHtml(String(failureText))}</span></td>
        <td><button class="rh-expand-btn" id="rh-btn-${detailId}" onclick="toggleRunDetail('${detailId}')">Details<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg></button></td>
      </tr>
      <tr class="rh-detail-row" id="rh-detail-${detailId}">
        <td colspan="7">
          <div class="rh-detail-inner">
            <div class="rh-detail-section"><div class="rh-detail-label">Results</div><div class="rh-detail-stat">${formatNumber(run.processed_rows)} <span>processed</span></div><div class="rh-detail-stat">${formatNumber(run.review_items)} <span>queued for review</span></div><div class="rh-detail-stat">${formatNumber(run.exported_rows)} <span>rows written to export files</span></div></div>
            <div class="rh-detail-section"><div class="rh-detail-label">Performance</div><div class="rh-detail-stat">${formatDecimal(run.throughput)} <span>img / sec</span></div><div class="rh-detail-stat">${escapeHtml(formatTimestampLabel(run.started_at))} → ${escapeHtml(formatTimestampLabel(run.finished_at || run.started_at))} <span>time range</span></div></div>
            <div class="rh-detail-section"><div class="rh-detail-label">Notes</div>${notes.length ? notes.map((note) => `<div class="rh-detail-stat">${escapeHtml(note)}</div>`).join("") : `<div class="rh-detail-stat">No backend notes recorded</div>`}</div>
          </div>
        </td>
      </tr>
    `;
  }

  function buildRunHistoryRows(status) {
    maybeRecordCompletedRun(status);
  
    const storedRuns = loadStoredRuns();
    const liveRun = status?.run_id ? snapshotRun(status) : null;
    const showLiveOnTop = liveRun && liveRun.status === "running";
    const dateRange = loadDateRange();
    const isFiltered = dateRange.from || dateRange.to;
  
    const rows = [];
    if (showLiveOnTop && matchesDateRange(liveRun, dateRange)) {
      rows.push(renderHistoryRow(liveRun, { isLive: true }));
    }
  
    for (const run of storedRuns) {
      if (showLiveOnTop && run.run_id === liveRun.run_id) continue;
      if (!matchesDateRange(run, dateRange)) continue;
      rows.push(renderHistoryRow(run));
    }
  
    if (rows.length === 0) {
      let message;
      if (isFiltered) {
        const rangeText = dateRange.from && dateRange.to
          ? `between ${dateRange.from} and ${dateRange.to}`
          : dateRange.from
            ? `from ${dateRange.from} onward`
            : `up to ${dateRange.to}`;
        message = `No runs found ${rangeText}. <a href="#" onclick="clearRunHistoryFilter();return false;" style="color:var(--blue)">Clear filter</a>`;
      } else {
        message = "No runs yet. Start a pipeline run from this page to see history here.";
      }
      return `<tr><td colspan="7" style="color:var(--muted);padding:18px 12px">${message}</td></tr>`;
    }
  
    return rows.join("");
  }

  function getRunSurfaceConfigs() {
    return [
      { kind: "main", buttonId: "run-btn", labelId: "run-btn-label", noteId: "run-ready-note", panelId: "run-progress", progressLabelId: "run-progress-label-text", fillId: "run-fill", etaId: "run-eta", statusId: "rs-status", stepId: "rs-step", discoveredId: "rs-discovered", downloadedId: "rs-downloaded", mlProgressId: "run-ml-progress", mlProgressSummaryId: "run-ml-progress-summary", mlProgressFillId: "run-ml-progress-fill", mlProcessedId: "run-ml-processed", mlTotalId: "run-ml-total", currentFileId: "run-current-file", logPathId: "run-log-path", errorId: "run-error-state" },
      { kind: "drive", buttonId: "drive-run-btn", labelId: "drive-run-btn-label", noteId: "drive-run-note", panelId: "drive-run-progress", progressLabelId: "drive-run-progress-label-text", fillId: "drive-run-fill", etaId: "drive-run-eta", statusId: "drive-rs-status", stepId: "drive-rs-step", discoveredId: "drive-rs-discovered", downloadedId: "drive-rs-downloaded", mlProgressId: "drive-run-ml-progress", mlProgressSummaryId: "drive-run-ml-progress-summary", mlProgressFillId: "drive-run-ml-progress-fill", mlProcessedId: "drive-run-ml-processed", mlTotalId: "drive-run-ml-total", currentFileId: "drive-run-current-file", logPathId: "drive-run-log-path", errorId: "drive-run-error-state" }
    ];
  }

  function applyDateFilter(range) {
    // Accept either an object {from, to} or a single string for backward compat
    let normalized;
    if (typeof range === "string") {
      normalized = { from: range, to: range };
    } else if (range && typeof range === "object") {
      normalized = {
        from: range.from || "",
        to: range.to || ""
      };
    } else {
      normalized = { from: "", to: "" };
    }
  
    saveDateRange(normalized);
  
    // Re-render the table
    const historyBody = document.getElementById("run-history-body");
    if (historyBody) {
      historyBody.innerHTML = buildRunHistoryRows(app.state.pipelineStatus);
    }
  
    // Show/hide clear button
    const hasFilter = !!(normalized.from || normalized.to);
    const clearBtn = document.getElementById("run-history-clear-btn");
    if (clearBtn) {
      clearBtn.style.display = hasFilter ? "inline-block" : "none";
    }
  
    // Sync the inputs in case this was called programmatically
    const fromInput = document.getElementById("run-history-date-from");
    const toInput = document.getElementById("run-history-date-to");
    if (fromInput && fromInput.value !== normalized.from) fromInput.value = normalized.from;
    if (toInput && toInput.value !== normalized.to) toInput.value = normalized.to;
  }
  
  function restoreDateFilter() {
    const saved = loadDateRange();
    const fromInput = document.getElementById("run-history-date-from");
    const toInput = document.getElementById("run-history-date-to");
    if (fromInput) fromInput.value = saved.from || "";
    if (toInput) toInput.value = saved.to || "";
    const clearBtn = document.getElementById("run-history-clear-btn");
    if (clearBtn) clearBtn.style.display = (saved.from || saved.to) ? "inline-block" : "none";
  }

  return {
    buildRunHistoryRows,
    getPipelinePanelSnapshot,
    getRunSurfaceConfigs,
    applyDateFilter,
    restoreDateFilter
  };
}
