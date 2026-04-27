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

export function createPipelineState(app) {
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

  function buildRunHistoryRows(status) {
    if (!status?.run_id) {
      return `<tr><td colspan="7" style="color:var(--muted);padding:18px 12px">No real backend run history is available yet. Start a pipeline run from this page to populate the latest run state.</td></tr>`;
    }

    const metrics = getPipelineMetrics(status);
    const batchLabel = status?.payload?.batch_size === "all" ? "All" : status?.payload?.batch_size || "Unknown";
    const statusClass = status?.status === "completed" ? "pill-green" : status?.status === "failed" ? "pill-red" : "pill-yellow";
    const statusLabel = status?.status === "completed" ? "Success" : status?.status === "failed" ? "Failed" : status?.status === "running" ? "Running" : "Idle";
    const failureText = metrics.failureCount === null ? "—" : formatNumber(metrics.failureCount);
    const durationText = status?.status === "running" ? "In progress" : (status?.result?.elapsed_seconds ? formatDurationLabel(status.result.elapsed_seconds) : "—");
    const imageCountText = metrics.manifestRows ? formatNumber(metrics.manifestRows) : batchLabel === "All" ? "All staged" : batchLabel;
    const detailId = String(status.run_id).replace(/[^a-zA-Z0-9_-]/g, "");
    const notes = Array.isArray(status?.result?.notes) ? status.result.notes : [];

    return `
      <tr>
        <td><span class="batch-num">${escapeHtml(String(status.run_id))}</span></td>
        <td>${escapeHtml(formatTimestampLabel(status.finished_at || status.started_at))}</td>
        <td>${escapeHtml(String(imageCountText))}</td>
        <td>${escapeHtml(durationText)}</td>
        <td><span class="status-pill ${statusClass}">${escapeHtml(statusLabel)}</span></td>
        <td><span class="${metrics.failureCount ? "failure-warn" : "failure-zero"}">${escapeHtml(String(failureText))}</span></td>
        <td><button class="rh-expand-btn" id="rh-btn-${detailId}" onclick="toggleRunDetail('${detailId}')">Details<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg></button></td>
      </tr>
      <tr class="rh-detail-row" id="rh-detail-${detailId}">
        <td colspan="7">
          <div class="rh-detail-inner">
            <div class="rh-detail-section"><div class="rh-detail-label">Results</div><div class="rh-detail-stat">${formatNumber(metrics.processedRows)} <span>processed</span></div><div class="rh-detail-stat">${formatNumber(metrics.reviewItems)} <span>queued for review</span></div><div class="rh-detail-stat">${formatNumber(metrics.exportedRows)} <span>rows written to export files</span></div></div>
            <div class="rh-detail-section"><div class="rh-detail-label">Performance</div><div class="rh-detail-stat">${formatDecimal(metrics.throughput)} <span>img / sec</span></div><div class="rh-detail-stat">${escapeHtml(formatTimestampLabel(status.started_at))} → ${escapeHtml(formatTimestampLabel(status.finished_at || status.started_at))} <span>time range</span></div></div>
            <div class="rh-detail-section"><div class="rh-detail-label">Notes</div>${notes.length ? notes.map((note) => `<div class="rh-detail-stat">${escapeHtml(note)}</div>`).join("") : `<div class="rh-detail-stat">No backend notes recorded</div>`}</div>
          </div>
        </td>
      </tr>
    `;
  }

  function getRunSurfaceConfigs() {
    return [
      { kind: "main", buttonId: "run-btn", labelId: "run-btn-label", noteId: "run-ready-note", panelId: "run-progress", progressLabelId: "run-progress-label-text", fillId: "run-fill", etaId: "run-eta", statusId: "rs-status", stepId: "rs-step", discoveredId: "rs-discovered", downloadedId: "rs-downloaded", mlProgressId: "run-ml-progress", mlProgressSummaryId: "run-ml-progress-summary", mlProgressFillId: "run-ml-progress-fill", mlProcessedId: "run-ml-processed", mlTotalId: "run-ml-total", currentFileId: "run-current-file", logPathId: "run-log-path", errorId: "run-error-state" },
      { kind: "drive", buttonId: "drive-run-btn", labelId: "drive-run-btn-label", noteId: "drive-run-note", panelId: "drive-run-progress", progressLabelId: "drive-run-progress-label-text", fillId: "drive-run-fill", etaId: "drive-run-eta", statusId: "drive-rs-status", stepId: "drive-rs-step", discoveredId: "drive-rs-discovered", downloadedId: "drive-rs-downloaded", mlProgressId: "drive-run-ml-progress", mlProgressSummaryId: "drive-run-ml-progress-summary", mlProgressFillId: "drive-run-ml-progress-fill", mlProcessedId: "drive-run-ml-processed", mlTotalId: "drive-run-ml-total", currentFileId: "drive-run-current-file", logPathId: "drive-run-log-path", errorId: "drive-run-error-state" }
    ];
  }

  return {
    buildRunHistoryRows,
    getPipelinePanelSnapshot,
    getRunSurfaceConfigs
  };
}
