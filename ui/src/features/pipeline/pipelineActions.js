/** Pipeline feature actions for slider updates, run submission, and history toggles. */
export function createPipelineActions(app, api, renderApi, loadPipelineStatus, loadPipelineResults) {
  function updateSlider(slider) {
    // const output = document.getElementById("threshold-val");
    // if (output) output.textContent = `${Number(slider.value)}%`;
    const value = Number(slider.value);
    const min = Number(slider.min) || 0;
    const max = Number(slider.max) || 100;
    const percent = ((value - min) / (max - min)) * 100;

    slider.style.background = `linear-gradient(to right, var(--blue) ${percent}%, #E2E8F0 ${percent}%)`;

    const output = document.getElementById("threshold-val");
    if (output) output.textContent = `${value}%`;
  }

  async function toggleRunModel(sourceModeOverride = null) {
    console.log("Running pipeline...");
    const sourceMode = sourceModeOverride || (app.state.uploadTab === "drive" ? "drive" : "local");
    if (app.state.runningModel) {
      return app.showToast("Pipeline stop is not wired yet. Check the backend status or log file for progress.", "warn");
    }

    const health = await app.refreshBackendHealth?.({ silent: true });
    if (!health?.connected) {
      return app.showToast("Backend offline. Start FastAPI on http://127.0.0.1:8000 before running the pipeline.", "warn");
    }

    if (sourceMode === "drive") {
      await app.features.drive.loadSelectedDriveFolderState({ silent: true });
      await app.features.drive.loadDriveSyncStatus({ silent: true });
      if (!app.state.driveConnected) return app.showToast(app.state.googleAuthActive ? "Confirm the Google Drive connection before running the pipeline from Drive mode" : "Connect Google Drive before running the pipeline from Drive mode", "warn");
      if (!app.state.selectedDriveFolder?.id) return app.showToast("Select a Google Drive folder before running the pipeline from Drive mode", "warn");
      if (app.state.driveSyncState.status === "syncing") return app.showToast("Drive sync is still in progress. Wait for it to finish before starting the pipeline.", "warn");
    }

    const threshold = Number(document.getElementById("threshold-slider")?.value || 80);
    const batchSize = document.getElementById("batch-select")?.value || "1000";
    try {
      const response = await api.runPipeline({
        source_mode: sourceMode,
        confidence_threshold: threshold,
        batch_size: batchSize,
        remove_burst_duplicates: true,
        exclude_humans: true
      });
      app.state.runningModel = true;
      renderApi.applyPipelineResults(null);
      if (sourceMode === "drive") {
        window.setTimeout(() => void app.features.drive.loadDriveSyncStatus({ silent: true }), 150);
      }
      await loadPipelineStatus({ silent: true });
      app.showToast(response.message || "Model run started", "success");
    } catch (error) {
      app.showToast(error.message || "Unable to start pipeline", "warn");
    } finally {
      renderApi.applyPipelineStatus(app.state.pipelineStatus);
    }
  }

  function toggleRunDetail(id) {
    const row = document.getElementById(`rh-detail-${id}`);
    const button = document.getElementById(`rh-btn-${id}`);
    const open = row?.classList.contains("open");
    row?.classList.toggle("open", !open);
    button?.classList.toggle("open", !open);
  }

  async function downloadPipelineResult(fileName) {
    try {
      const result = await api.downloadPipelineResultFile(fileName);
      const objectUrl = window.URL.createObjectURL(result.blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = result.fileName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(objectUrl);
      app.showToast(`Downloaded ${result.fileName}`, "success");
    } catch (error) {
      app.showToast(error.message || "Unable to download pipeline result", "warn");
    }
  }

  return {
    downloadPipelineResult,
    loadPipelineResults,
    toggleDriveRunModel: () => toggleRunModel("drive"),
    toggleRunDetail,
    toggleRunModel,
    updateSlider
  };
}
