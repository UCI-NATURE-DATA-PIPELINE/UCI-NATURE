/** Drive feature view events for tabs, upload pause, and local selection cards. */
import { appState } from "../../state/appState.js";

export function createDriveEvents(app, renderApi) {
  function switchUploadTab(tab) {
    appState.uploadTab = tab;
    document.getElementById("upload-manual")?.style.setProperty("display", tab === "manual" ? "block" : "none");
    document.getElementById("upload-drive")?.style.setProperty("display", tab === "drive" ? "block" : "none");
    document.getElementById("tab-manual")?.classList.toggle("active", tab === "manual");
    document.getElementById("tab-drive")?.classList.toggle("active", tab === "drive");
    renderApi.updatePipelineSourceSummary();
    if (tab === "drive" && appState.driveConnected) {
      void app.features.drive.hydrateDriveFolderSelection({ silent: true });
      void app.features.drive.loadDriveSyncStatus({ silent: true });
    }
  }

  function togglePause(button) {
    appState.uploadPaused = !appState.uploadPaused;
    document.getElementById("upload-status-pill").textContent = appState.uploadPaused ? "Paused" : "Uploading…";
    document.getElementById("pause-label").textContent = appState.uploadPaused ? "Resume" : "Pause";
    if (!appState.uploadPaused) {
      document.getElementById("upload-prog-fill")?.style.setProperty("width", "68%");
      const pct = document.getElementById("upload-prog-pct");
      if (pct) pct.textContent = "68%";
    }
    button.dataset.paused = appState.uploadPaused ? "true" : "false";
    app.showToast(appState.uploadPaused ? "Upload paused" : "Upload resumed", appState.uploadPaused ? "warn" : "success");
  }

  function selectLocCard(card) {
    card?.closest(".location-select-grid")?.querySelectorAll(".loc-select-card").forEach((element) => element.classList.remove("selected"));
    card.classList.add("selected");
  }

  function selectDriveLocCard(card) {
    if (appState.driveSyncState.status === "syncing") return app.showToast("Wait for the current Drive sync to finish before changing folder settings", "warn");
    if (!appState.googleAuthActive) return app.showToast("Sign in with Google first", "warn");
    if (!appState.driveConnected) return app.showToast("Confirm the Google Drive connection first", "warn");
    if (card?.dataset?.driveCreate === "true") {
      appState.driveCreateSiteMode = true;
      renderApi.syncDriveLocationCards();
      renderApi.syncDriveCustomSiteState();
      document.getElementById("drive-site-custom-input")?.focus();
      return;
    }
    const locationEl = document.getElementById("drive-camera-location-select");
    if (!locationEl) return;
    const selectedLocation = String(card?.dataset?.driveLocation || "").trim();
    appState.driveCreateSiteMode = false;
    locationEl.value = selectedLocation;
    void app.features.drive.handleDriveSyncSettingsChange();
  }

  function handleDriveManualSelectionKeydown(event) {
    if (event?.key !== "Enter") return;
    event.preventDefault();
    void app.features.drive.applyManualDriveFolderSelection();
  }

  return {
    handleDriveManualSelectionKeydown,
    selectLocCard,
    selectDriveLocCard,
    switchUploadTab,
    togglePause
  };
}
