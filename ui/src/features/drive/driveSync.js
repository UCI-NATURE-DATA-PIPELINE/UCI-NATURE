/** Drive feature sync and manual-selection workflows. */
import { appState } from "../../state/appState.js";
import { normalizeDriveSyncStatus } from "../../utils/helpers.js";

export function createDriveSync(app, api, stateApi, renderApi) {
  let driveSyncPollId = null;

  async function loadDriveSyncStatus({ silent = false } = {}) {
    if (!appState.signedInUser && !localStorage.getItem("token")) {
      stateApi.applyDriveSyncStatus(null);
      renderApi.syncDriveUI();
      renderApi.renderDriveFolderSelection();
      stopDriveSyncPolling();
      return appState.driveSyncState;
    }
    try {
      const sync = await api.getDriveSyncStatus();
      stateApi.applyDriveSyncStatus(sync);
      renderApi.syncDriveUI();
      renderApi.renderDriveFolderSelection();
      updateDriveSyncPollingState();
      return sync;
    } catch (error) {
      if (!silent) app.showToast(error.message || "Unable to load Drive sync status", "warn");
      return appState.driveSyncState;
    }
  }

  function updateDriveSyncPollingState() {
    if (appState.driveSyncState.status === "syncing") startDriveSyncPolling();
    else stopDriveSyncPolling();
  }

  function startDriveSyncPolling() {
    if (driveSyncPollId) return;
    driveSyncPollId = window.setInterval(() => void loadDriveSyncStatus({ silent: true }), 1200);
  }

  function stopDriveSyncPolling() {
    if (!driveSyncPollId) return;
    window.clearInterval(driveSyncPollId);
    driveSyncPollId = null;
  }

  async function triggerSync(buttonEl) {
    if (!appState.googleAuthActive) return app.showToast("Connect Google Drive before syncing a Drive folder", "warn");
    if (!appState.driveConnected) return app.showToast("Confirm the Google Drive connection before syncing", "warn");
    if (!appState.selectedDriveFolder?.id) return app.showToast("Select a Google Drive folder before syncing", "warn");
    if (appState.driveSyncState.status === "syncing") {
      app.showToast("A Drive sync is already in progress", "warn");
      startDriveSyncPolling();
      return;
    }

    const originalHtml = buttonEl?.innerHTML;
    if (buttonEl) {
      buttonEl.disabled = true;
      buttonEl.textContent = "Syncing...";
    }
    appState.driveFolderError = "";
    stateApi.applyDriveSyncStatus({ ...normalizeDriveSyncStatus(null), status: "syncing", source_ready: false, started_at: new Date().toISOString(), folder: { id: appState.selectedDriveFolder.id, name: appState.selectedDriveFolder.name }, selected_folder: appState.selectedDriveFolder, selected_folder_matches: true, staging_dir: appState.driveSyncState.staging_dir || "data/staging", last_sync_message: `Syncing ${appState.selectedDriveFolder.name} into backend staging` });
    renderApi.syncDriveUI();
    renderApi.renderDriveFolderSelection();
    startDriveSyncPolling();
    try {
      const syncRequest = api.syncSelectedDriveFolder(appState.driveSyncLimit);
      window.setTimeout(() => void loadDriveSyncStatus({ silent: true }), 150);
      const response = await syncRequest;
      appState.selectedDriveFolder = response?.folder || appState.selectedDriveFolder;
      stateApi.applySelectedDriveFolderSettings(appState.selectedDriveFolder);
      stateApi.applyDriveSyncStatus(response?.sync || null);
      renderApi.syncDriveUI();
      renderApi.renderDriveFolderSelection();
      stopDriveSyncPolling();
      const stagedCount = Number(appState.driveSyncState.downloaded_count || appState.driveSyncState.discovered_count || 0);
      if (appState.driveSyncState.status === "cancelled") {
        app.showToast("Drive sync stopped", "warn");
      } else {
        app.showToast(response?.message || `Synced ${stagedCount} image${stagedCount === 1 ? "" : "s"}`, "success");
      }
    } catch (error) {
      appState.driveFolderError = error.message || "Unable to sync the selected Drive folder";
      await loadDriveSyncStatus({ silent: true });
      app.showToast(appState.driveFolderError, "warn");
    } finally {
      if (buttonEl) {
        buttonEl.disabled = false;
        buttonEl.innerHTML = originalHtml || "Sync Now";
      }
    }
  }

  async function cancelDriveSync() {
    if (appState.driveSyncState.status !== "syncing") {
      app.showToast("No Drive sync is running", "warn");
      return;
    }
    try {
      const response = await api.cancelDriveSync();
      stateApi.applyDriveSyncStatus(response?.sync || { ...appState.driveSyncState, status: "cancelled", cancellation_requested: true });
      renderApi.syncDriveUI();
      renderApi.renderDriveFolderSelection();
      stopDriveSyncPolling();
      app.showToast(response?.message || "Drive sync stop requested", "warn");
    } catch (error) {
      app.showToast(error.message || "Unable to stop Drive sync", "warn");
    }
  }

  return {
    cancelDriveSync,
    loadDriveSyncStatus,
    startDriveSyncPolling,
    stopDriveSyncPolling,
    triggerSync,
    updateDriveSyncPollingState
  };
}
