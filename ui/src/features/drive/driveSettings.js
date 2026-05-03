/** Drive feature handlers for manual folder selection and sync setting updates. */
import { appState } from "../../state/appState.js";
import {
  normalizeDriveFolderOptions,
  normalizeDriveSyncLimitValue,
  normalizeDriveSyncStatus
} from "../../utils/helpers.js";

export function createDriveSettings(app, api, stateApi, renderApi, selectionApi) {
  const DRIVE_SITE_PRESETS = ["Site 1", "Site 2", "Site 3", "Site 4"];

  function isPresetDriveSite(value) {
    return DRIVE_SITE_PRESETS.includes(String(value || "").trim());
  }

  async function applyManualDriveFolderSelection() {
    const inputEl = document.getElementById("drive-folder-manual-input");
    const rawValue = String(inputEl?.value || "").trim();
    if (!appState.googleAuthActive) return app.showToast("Sign in with Google first", "warn");
    if (!appState.driveConnected) return app.showToast("Confirm the Google Drive connection first", "warn");
    if (appState.driveSyncState.status === "syncing") return app.showToast("Wait for the current Drive sync to finish before changing folders", "warn");
    if (!rawValue) {
      renderApi.setDriveManualSelectionFeedback("Paste a Google Drive folder URL or raw folder ID first.", "error");
      renderApi.syncDriveManualSelectionState();
      return;
    }

    appState.driveManualSelectionPending = true;
    renderApi.setDriveManualSelectionFeedback("Checking that Drive folder in the backend…", "muted");
    renderApi.syncDriveManualSelectionState();

    try {
      const response = await api.saveSelectedDriveFolder(rawValue, null, appState.driveCameraLocation || null, appState.driveSyncLimit);
      const folder = response?.folder || null;
      if (!folder?.id || !folder?.name) throw new Error("The backend did not return a valid Google Drive folder.");
      appState.selectedDriveFolder = folder;
      stateApi.applySelectedDriveFolderSettings(appState.selectedDriveFolder);
      appState.availableDriveFolders = normalizeDriveFolderOptions([...appState.availableDriveFolders, folder]);
      appState.driveSyncState = normalizeDriveSyncStatus(response?.sync || null);
      appState.driveFolderError = "";
      if (inputEl) inputEl.value = "";
      document.getElementById("drive-manual-popover")?.removeAttribute("open");
      renderApi.setDriveManualSelectionFeedback(`Selected Drive folder: ${folder.name}.`, "success");
      renderApi.syncDriveUI();
      renderApi.renderDriveFolderSelection();
    } catch (error) {
      const message = error.message || "Unable to select that Google Drive folder";
      renderApi.setDriveManualSelectionFeedback(message, "error");
      app.showToast(message, "warn");
    } finally {
      appState.driveManualSelectionPending = false;
      renderApi.syncDriveManualSelectionState();
    }
  }

  function handleDriveDateRangeChange() {
    const startEl = document.getElementById("drive-date-start");
    const endEl = document.getElementById("drive-date-end");
    const flagEl = document.getElementById("drive-date-flag");
    appState.driveDateRangeStart = String(startEl?.value || "");
    appState.driveDateRangeEnd = String(endEl?.value || "");
    appState.driveFlagOutsideRange = Boolean(flagEl?.checked);
    renderApi.syncDriveUI();
  }

  async function handleDriveSyncSettingsChange() {
    const locationEl = document.getElementById("drive-camera-location-select");
    const limitEl = document.getElementById("drive-sync-limit-select");
    if (appState.driveSyncState.status === "syncing") {
      renderApi.syncDriveSelectionControls();
      return app.showToast("Wait for the current Drive sync to finish before changing sync settings", "warn");
    }

    appState.driveCameraLocation = String(locationEl?.value || "").trim();
    appState.driveCreateSiteMode = Boolean(appState.driveCameraLocation && !isPresetDriveSite(appState.driveCameraLocation));
    appState.driveSyncLimit = normalizeDriveSyncLimitValue(limitEl?.value || "");
    if (!appState.selectedDriveFolder?.id || (!appState.signedInUser && !localStorage.getItem("token"))) {
      renderApi.syncDriveUI();
      renderApi.renderDriveFolderSelection();
      return;
    }

    try {
      const response = await api.saveSelectedDriveFolder(appState.selectedDriveFolder.id, appState.selectedDriveFolder.name, appState.driveCameraLocation || null, appState.driveSyncLimit);
      appState.selectedDriveFolder = response?.folder || { ...appState.selectedDriveFolder, camera_location: appState.driveCameraLocation || null, max_files: appState.driveSyncLimit };
      stateApi.applySelectedDriveFolderSettings(appState.selectedDriveFolder);
      appState.driveSyncState = normalizeDriveSyncStatus(response?.sync || null);
      appState.driveFolderError = "";
    } catch (error) {
      appState.driveFolderError = error.message || "Unable to save Drive sync settings";
      stateApi.applySelectedDriveFolderSettings(appState.selectedDriveFolder);
      app.showToast(appState.driveFolderError, "warn");
    } finally {
      renderApi.syncDriveUI();
      renderApi.renderDriveFolderSelection();
    }
  }

  async function applyDriveCustomSite() {
    const inputEl = document.getElementById("drive-site-custom-input");
    const locationEl = document.getElementById("drive-camera-location-select");
    const customSite = String(inputEl?.value || "").trim();
    if (appState.driveSyncState.status === "syncing") return app.showToast("Wait for the current Drive sync to finish before changing folder settings", "warn");
    if (!appState.googleAuthActive) return app.showToast("Sign in with Google first", "warn");
    if (!appState.driveConnected) return app.showToast("Confirm the Google Drive connection first", "warn");
    if (!customSite) {
      renderApi.syncDriveCustomSiteState();
      return app.showToast("Enter a camera site name first", "warn");
    }
    if (!locationEl) return;
    appState.driveCreateSiteMode = true;
    const existingOption = Array.from(locationEl.options).find((option) => option.value === customSite);
    if (!existingOption) {
      const customOption = document.createElement("option");
      customOption.value = customSite;
      customOption.textContent = customSite;
      customOption.dataset.driveCustom = "true";
      locationEl.appendChild(customOption);
    }
    locationEl.value = customSite;
    await handleDriveSyncSettingsChange();
    renderApi.syncDriveCustomSiteState();
    app.showToast(`Using camera site: ${customSite}`, "success");
  }

  function handleDriveCustomSiteKeydown(event) {
    if (event?.key !== "Enter") return;
    event.preventDefault();
    void applyDriveCustomSite();
  }

  async function refreshDriveFolders() {
    if (!appState.googleAuthActive) return app.showToast("Sign in with Google first", "warn");
    if (!appState.driveConnected) return app.showToast("Confirm the Google Drive connection first", "warn");
    if (appState.driveSyncState.status === "syncing") return app.showToast("Wait for the current Drive sync to finish before refreshing folders", "warn");
    const result = await selectionApi.hydrateDriveFolderSelection();
    if (!appState.driveFolderError) {
      renderApi.setDriveManualSelectionFeedback(null);
      app.showToast(result.folders.length ? `Loaded ${result.folders.length} Drive folder${result.folders.length === 1 ? "" : "s"}` : "No Drive folders available", result.folders.length ? "success" : "warn");
    }
  }

  return {
    applyManualDriveFolderSelection,
    applyDriveCustomSite,
    handleDriveCustomSiteKeydown,
    handleDriveDateRangeChange,
    handleDriveSyncSettingsChange,
    refreshDriveFolders
  };
}
