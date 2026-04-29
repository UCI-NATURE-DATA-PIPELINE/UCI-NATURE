/** Pipeline rendering for run status surfaces and backend run history. */
import { escapeHtml, formatNumber, formatTimestampLabel } from "../../utils/format.js";

export function createPipelineRender(app, stateApi) {
  function setPipelineDetailValue(element, value, fallback = "—") {
    if (!element) return;
    const hasValue = !(value === null || value === undefined || (typeof value === "string" && value.trim() === ""));
    const text = hasValue ? String(value) : fallback;
    element.textContent = text;
    element.title = hasValue ? text : "";
  }

  function applyPipelineStatusToSurface(surface, status) {
    const state = status?.status || "idle";
    const snapshot = stateApi.getPipelinePanelSnapshot(status);
    const button = document.getElementById(surface.buttonId);
    const label = document.getElementById(surface.labelId);
    const note = document.getElementById(surface.noteId);
    const panel = document.getElementById(surface.panelId);
    const progressLabel = document.getElementById(surface.progressLabelId);
    const fill = document.getElementById(surface.fillId);
    const eta = document.getElementById(surface.etaId);
    const statusValue = document.getElementById(surface.statusId);
    const stepValue = document.getElementById(surface.stepId);
    const discoveredValue = document.getElementById(surface.discoveredId);
    const downloadedValue = document.getElementById(surface.downloadedId);
    const mlWrap = document.getElementById(surface.mlProgressId);
    const mlSummary = document.getElementById(surface.mlProgressSummaryId);
    const mlFill = document.getElementById(surface.mlProgressFillId);
    const mlProcessed = document.getElementById(surface.mlProcessedId);
    const mlTotal = document.getElementById(surface.mlTotalId);
    const currentFile = document.getElementById(surface.currentFileId);
    const logPath = document.getElementById(surface.logPathId);
    const errorValue = document.getElementById(surface.errorId);

    if (button) {
      button.classList.remove("idle", "running");
      button.classList.add(state === "running" ? "running" : "idle");
      button.disabled = state === "running" || (surface.kind === "drive" && !app.features.drive.canRunDrivePipeline());
    }
    if (label) label.textContent = state === "running" ? "Pipeline Running" : surface.kind === "drive" ? "Run Pipeline (Drive Source)" : "Run Detection & Classification";
    if (note) {
      if (state === "running") note.textContent = status?.progress?.step || `Run ${status.run_id} started ${formatTimestampLabel(status.started_at)}.`;
      else if (state === "completed") note.textContent = `Last run ${status.run_id} completed ${formatTimestampLabel(status.finished_at)}.`;
      else if (state === "failed") note.textContent = status.error ? `Last run ${status.run_id} failed: ${status.error}` : `Last run ${status.run_id} failed.`;
      else note.textContent = surface.kind === "drive" || app.state.uploadTab === "drive" ? app.features.drive.getDriveRunIdleNote() : "Ready to start a backend pipeline run";
    }
  
    if (panel) panel.style.display = (!status || state === "idle") ? "none" : "block";
    if (progressLabel) progressLabel.textContent = state === "running" ? status?.progress?.step || "Pipeline running in backend" : state === "completed" ? "Latest run completed" : state === "failed" ? "Latest run failed" : "No active pipeline run";
    if (eta) eta.textContent = state === "running" ? status?.progress?.message || status?.latest_log_line || "Backend log is updating" : state === "completed" ? `Completed ${formatTimestampLabel(status.finished_at)}` : state === "failed" ? status.error || "See backend log for details" : surface.kind === "drive" ? "Run becomes available once a Drive folder is selected" : "No active run";
    if (fill) fill.style.width = state === "completed" || state === "failed" ? "100%" : state === "running" ? `${app.features.drive.getDriveSyncStepPercent()}%` : "0%";
    if (statusValue) statusValue.textContent = snapshot.overallStatus;
    if (stepValue) setPipelineDetailValue(stepValue, snapshot.currentStep, "Waiting for a run");
    if (discoveredValue) discoveredValue.textContent = snapshot.discovered === null ? "—" : formatNumber(snapshot.discovered);
    if (downloadedValue) downloadedValue.textContent = snapshot.downloaded === null ? "—" : formatNumber(snapshot.downloaded);
    if (mlWrap) mlWrap.style.display = snapshot.mlActive ? "block" : "none";
    if (mlSummary) mlSummary.textContent = snapshot.mlActive ? `${formatNumber(snapshot.processedImages || 0)} / ${formatNumber(snapshot.totalImages || 0)} images` : "—";
    if (mlFill) mlFill.style.width = snapshot.mlActive ? `${snapshot.mlProgressPercent}%` : "0%";
    if (mlProcessed) mlProcessed.textContent = snapshot.mlActive ? formatNumber(snapshot.processedImages || 0) : "—";
    if (mlTotal) mlTotal.textContent = snapshot.mlActive ? formatNumber(snapshot.totalImages || 0) : "—";
    setPipelineDetailValue(currentFile, snapshot.currentFile);
    setPipelineDetailValue(logPath, snapshot.logPath);
    setPipelineDetailValue(errorValue, snapshot.error);
  }

  function applyPipelineStatus(status) {
    app.state.pipelineStatus = status;
    app.state.runningModel = (status?.status || "idle") === "running";
    stateApi.getRunSurfaceConfigs().forEach((surface) => applyPipelineStatusToSurface(surface, status));
    const state = String(status?.status || "idle").toLowerCase();
    const panelVisible = !!status && state !== "idle";
    const historyWrap = document.getElementById("run-history-wrap");
    if (historyWrap) historyWrap.classList.toggle("has-active-run", panelVisible);

    const historyBody = document.getElementById("run-history-body");
    const historyNote = document.getElementById("run-history-note");
    if (historyBody) historyBody.innerHTML = stateApi.buildRunHistoryRows(status);
    if (historyNote) historyNote.textContent = status?.run_id ? "Latest backend run" : "No real run history yet";
    app.features.drive.syncDriveUI();


  }

  function buildPipelineResultRows(files = []) {
    if (!files.length) {
      return `<tr><td colspan="4" style="padding:14px 12px;color:var(--muted)">No export CSV files are available yet.</td></tr>`;
    }

    return files.map((file) => {
      const fileName = file.name || "";
      const downloadArg = escapeHtml(JSON.stringify(fileName));

      return `
      <tr>
        <td style="padding:12px">${escapeHtml(fileName || "Unknown")}</td>
        <td style="padding:12px">${formatNumber(file.rows || 0)}</td>
        <td style="padding:12px">${escapeHtml(file.path || "—")}</td>
        <td style="padding:12px"><button class="btn btn-outline btn-sm" onclick="downloadPipelineResult(${downloadArg})">Download CSV</button></td>
      </tr>
    `;
    }).join("");
  }

  function applyPipelineResults(results) {
    app.state.pipelineResults = results;
    const note = document.getElementById("pipeline-results-note");
    const summary = document.getElementById("pipeline-results-summary");
    const tableBody = document.getElementById("pipeline-results-body");

    if (note) {
      note.textContent = results?.status === "ready"
        ? `Results ready from run ${results.run_id || "latest"}`
        : app.state.runningModel
          ? "Waiting for the backend pipeline to finish…"
          : "Run the pipeline to generate export-ready CSV files.";
    }
    if (summary) {
      summary.textContent = results?.status === "ready"
        ? `${formatNumber(results.file_count || 0)} file(s) · ${formatNumber(results.total_rows || 0)} rows · ${results.output_dir || "data/outputs/by_location"}`
        : results?.message || "No completed pipeline results are available yet.";
    }
    if (tableBody) {
      tableBody.innerHTML = buildPipelineResultRows(results?.files || []);
    }
  }

  return {
    applyPipelineResults,
    applyPipelineStatus
  };
}
