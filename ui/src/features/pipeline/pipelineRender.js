import { escapeHtml, formatDecimal, formatNumber, formatTimestampLabel } from "../../utils/format.js";
import { getPipelineMetrics } from "../../utils/helpers.js";

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
    const isRunning = state === "running";
    const isCompleted = state === "completed";
    const isFailed = state === "failed";
    const isVisible = isRunning || isCompleted || isFailed;
    const snapshot = stateApi.getPipelinePanelSnapshot(status);
    const metrics = getPipelineMetrics(status);
    const throughputValue = document.getElementById("rs-throughput");
    const failuresValue = document.getElementById("rs-failures");
    const button = document.getElementById(surface.buttonId);
    const stopButton = document.getElementById(surface.stopButtonId);
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
    const processedValue = document.getElementById("rs-processed");
    const remainingValue = document.getElementById("rs-remaining");

    if (button) {
      button.classList.remove("idle", "running");
      button.classList.add(isRunning ? "running" : "idle");
      button.disabled = isRunning || (surface.kind === "drive" && !app.features.drive.canRunDrivePipeline());
    }
    if (stopButton) {
      stopButton.style.display = isRunning ? "inline-flex" : "none";
      stopButton.disabled = Boolean(status?.cancellation_requested);
      stopButton.textContent = status?.cancellation_requested ? "Stopping..." : "Stop";
    }
    if (label) label.textContent = isRunning ? "Pipeline Running" : surface.kind === "drive" ? "Run Pipeline (Drive Source)" : "Run Pipeline";
    if (note) {
      if (isRunning) note.textContent = status?.progress?.step || `Run ${status.run_id} started ${formatTimestampLabel(status.started_at)}.`;
      else if (isCompleted) note.textContent = `Last run ${status.run_id} completed ${formatTimestampLabel(status.finished_at)}.`;
      else if (state === "cancelled") note.textContent = `Last run ${status.run_id} was stopped.`;
      else if (isFailed) note.textContent = status.error ? `Last run ${status.run_id} failed: ${status.error}` : `Last run ${status.run_id} failed.`;
      else note.textContent = surface.kind === "drive" || app.state.uploadTab === "drive" ? app.features.drive.getDriveRunIdleNote() : "Click Run to start pipeline.";
    }
    if (panel) {
      panel.style.display = isVisible ? "block" : "none";
      panel.classList.remove("state-running", "state-completed", "state-failed");
      if (isRunning) panel.classList.add("state-running");
      else if (isCompleted) panel.classList.add("state-completed");
      else if (isFailed) panel.classList.add("state-failed");
    }
    if (progressLabel) progressLabel.textContent = isRunning ? status?.progress?.step || "Processing images…" : isCompleted ? "Processing Complete" : isFailed ? "Pipeline Failed" : "No active pipeline run";
    if (eta) eta.textContent = isRunning ? status?.progress?.message || status?.latest_log_line || "Backend log is updating" : isCompleted ? `Completed ${formatTimestampLabel(status.finished_at)}` : state === "cancelled" ? "Stopped by user" : isFailed ? status.error || "See backend log for details" : surface.kind === "drive" ? "Run becomes available once a Drive folder is selected" : "No active run";
    if (fill) {
      fill.style.width = isCompleted || isFailed ? "100%" : isRunning ? `${app.features.drive.getDriveSyncStepPercent()}%` : "0%";
      fill.classList.remove("state-completed", "state-failed");
      if (isCompleted) fill.classList.add("state-completed");
      if (isFailed) fill.classList.add("state-failed");
    }
    const liveProcessedCount = Number.isFinite(Number(snapshot.processedImages)) ? Number(snapshot.processedImages) : null;
    const liveTotalCount = Number.isFinite(Number(snapshot.totalImages)) ? Number(snapshot.totalImages) : null;
    const terminalProcessedCount = Number.isFinite(Number(metrics.processedRows)) ? Number(metrics.processedRows) : null;
    const terminalTotalCount = Number.isFinite(Number(metrics.manifestRows)) ? Number(metrics.manifestRows) : null;
    const processedCount = isRunning
      ? (liveProcessedCount ?? terminalProcessedCount)
      : (terminalProcessedCount ?? liveProcessedCount);
    const totalCount = isRunning
      ? (liveTotalCount ?? terminalTotalCount)
      : (terminalTotalCount ?? liveTotalCount);
    const remainingCount = totalCount !== null && processedCount !== null
      ? Math.max(totalCount - processedCount, 0)
      : null;
    if (processedValue) {
      processedValue.textContent = processedCount === null ? "—" : formatNumber(processedCount);
    }
    if (remainingValue) {
      remainingValue.textContent = remainingCount === null ? "—" : formatNumber(remainingCount);
    }
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

    if (throughputValue) {
      throughputValue.textContent = metrics.throughput ? formatDecimal(metrics.throughput) : "—";
    }
    if (failuresValue) {
      failuresValue.textContent = metrics.failureCount === null ? "—" : formatNumber(metrics.failureCount);
      failuresValue.style.color = metrics.failureCount ? "#E53E3E" : "";
    }
  }

  function applyPipelineStatus(status) {
    app.state.pipelineStatus = status;
    app.state.runningModel = (status?.status || "idle") === "running";
    stateApi.getRunSurfaceConfigs().forEach((surface) => applyPipelineStatusToSurface(surface, status));
    const state = String(status?.status || "idle").toLowerCase();
    const panelVisible = state === "running" || state === "completed" || state === "failed";
    const historyWrap = document.getElementById("run-history-wrap");
    if (historyWrap) historyWrap.classList.toggle("has-active-run", panelVisible);

    const historyBody = document.getElementById("run-history-body");
    const historyNote = document.getElementById("run-history-note");
    if (historyBody) historyBody.innerHTML = stateApi.buildRunHistoryRows(status);
    if (stateApi.restoreDateFilter) stateApi.restoreDateFilter();
    if (historyNote) {
      const stored = JSON.parse(localStorage.getItem("uci_nature_run_history") || "[]");
      const count = stored.length;
      if (count > 0) {
        historyNote.textContent = `${count} run${count === 1 ? "" : "s"} stored`;
      } else if (status?.run_id) {
        historyNote.textContent = "Latest backend run";
      } else {
        historyNote.textContent = "";
      }
    }
    app.features.drive.syncDriveUI();
    app.features.dashboard?.applyDashboardPipelineState?.(status);
  }

  // function buildPipelineResultRows(files = []) {
  //   if (!files.length) {
  //     return `<tr><td colspan="3" style="padding:14px 12px;color:var(--muted)">No results are available yet.</td></tr>`;
  //   }

  //   return files.map((file) => {
  //     const fileName = file.name || "";
  //     const baseLabel = file.label || fileName.replace(/\.csv$/i, "") || "Unknown";
  //     const isPrimary = fileName === "final_results.csv";
  //     const tag = isPrimary
  //       ? `<span style="margin-left:8px;font-size:11px;font-weight:600;color:#2B6CB0;background:#EBF8FF;border:1px solid #BEE3F8;padding:2px 7px;border-radius:6px">Main file</span>`
  //       : "";
  //     const downloadArg = escapeHtml(JSON.stringify(fileName));

  //     return `
  //     <tr${isPrimary ? ' style="background:#F7FAFC"' : ""}>
  //       <td style="padding:12px">${escapeHtml(baseLabel)}${tag}</td>
  //       <td style="padding:12px">${formatNumber(file.rows || 0)}</td>
  //       <td style="padding:12px"><button class="btn btn-outline btn-sm" onclick="downloadPipelineResult(${downloadArg})">Download</button></td>
  //     </tr>
  //   `;
  //   }).join("");
  // }

  // function applyPipelineResults(results) {
  //   app.state.pipelineResults = results;
  //   const note = document.getElementById("pipeline-results-note");
  //   const summary = document.getElementById("pipeline-results-summary");
  //   const tableBody = document.getElementById("pipeline-results-body");

  //   if (note) {
  //     note.textContent = results?.status === "ready"
  //       ? "Results are ready"
  //       : app.state.runningModel
  //         ? "Processing your images…"
  //         : "Run the pipeline to generate results.";
  //   }
  //   if (summary) {
  //     summary.textContent = results?.status === "ready"
  //       ? `${formatNumber(results.file_count || 0)} file(s) · ${formatNumber(results.total_rows || 0)} records`
  //       : results?.message || "No results are available yet.";
  //   }
  //   if (tableBody) {
  //     tableBody.innerHTML = buildPipelineResultRows(results?.files || []);
  //   }
  // }

  function applyPipelineResults(results) {
    if (results && results.exports) {
      results = results.exports;
    }
    app.state.pipelineResults = results;
    
    const emptyState = document.getElementById('insights-empty-state');
    const dashboard = document.getElementById('insights-dashboard');
    const downloadBtn = document.getElementById('download-latest-csv');

    const hasFiles = results && Array.isArray(results.files) && results.files.length > 0;
    const isReady = results && (results.status === "ready" || hasFiles);

    if (!isReady) {
      if (emptyState) emptyState.style.display = 'block';
      if (dashboard) dashboard.style.display = 'none';
      if (downloadBtn) downloadBtn.style.display = 'none';
      
      if (emptyState && app.state.runningModel) {
        emptyState.textContent = "Processing your images…";
      } else if (emptyState) {
        emptyState.textContent = "Run the pipeline or select a historical run to view insights.";
      }
      return;
    }

    if (emptyState) emptyState.style.display = 'none';
    if (dashboard) dashboard.style.display = 'block';
    
    if (downloadBtn) {
      downloadBtn.style.display = 'inline-flex';
      const mainFile = (results.files || []).find(f => f.name === 'final_results.csv' || f.name === 'results.csv') || results.files?.[0];
      
      if (mainFile) {
        downloadBtn.onclick = () => {
          if (typeof window.downloadPipelineResult === 'function') {
            window.downloadPipelineResult(mainFile.name);
          }
        };
      } else {
        downloadBtn.style.display = 'none';
      }
    }

    const imagesWithAnimals = results.images_with_animals;
    const totalEl = document.getElementById('insight-total-animals');
    
    if (imagesWithAnimals === undefined) {
       if (totalEl) totalEl.textContent = "N/A";
    } else {
       if (totalEl) totalEl.textContent = formatNumber(imagesWithAnimals);
    }

    const speciesListElement = document.getElementById('insight-species-list');
    if (speciesListElement) {
      speciesListElement.innerHTML = ''; 
      
      const speciesCounts = results.species_counts || {};
      const sortedSpecies = Object.entries(speciesCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3);

      if (sortedSpecies.length === 0) {
        speciesListElement.innerHTML = '<li style="color: #94a3b8; border: none; padding-bottom: 0; justify-content: center;">Detailed species breakdown not available for this run.</li>';
      } else {
        sortedSpecies.forEach(([species, count]) => {
          speciesListElement.innerHTML += `
            <li>
              <span>${escapeHtml(species)}</span> 
              <span>${formatNumber(count)}</span>
            </li>`;
        });
      }
    }
  }

  return {
    applyPipelineResults,
    applyPipelineStatus
  };
}
