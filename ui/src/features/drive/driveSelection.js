/** Drive feature data-loading and folder-selection workflows. */
import { appState } from "../../state/appState.js";
import { normalizeDriveFolderOptions, normalizeDriveSyncStatus } from "../../utils/helpers.js";

export function createDriveSelection(app, api, stateApi, renderApi) {
  async function loadSelectedDriveFolderState({ silent = true } = {}) {
    if (!appState.signedInUser && !localStorage.getItem("token")) return appState.selectedDriveFolder;
    try {
      const response = await api.getSelectedDriveFolder();
      appState.selectedDriveFolder = response?.folder || null;
      stateApi.applySelectedDriveFolderSettings(appState.selectedDriveFolder);
      if (response?.sync) appState.driveSyncState = normalizeDriveSyncStatus(response.sync);
      appState.driveFolderError = "";
      return appState.selectedDriveFolder;
    } catch (error) {
      appState.driveFolderError = error.message || "Unable to load selected Drive folder";
      if (!silent) app.showToast(appState.driveFolderError, "warn");
      return null;
    } finally {
      renderApi.syncDriveUI();
      renderApi.renderDriveFolderSelection();
    }
  }

  async function hydrateDriveFolderSelection({ silent = false } = {}) {
    if (!appState.googleAuthActive || !appState.driveConnected) {
      appState.availableDriveFolders = [];
      appState.driveFoldersLoading = false;
      appState.driveFolderError = "";
      renderApi.renderDriveFolderSelection();
      return { folders: [], selectedFolder: appState.selectedDriveFolder };
    }

    appState.driveFoldersLoading = true;
    appState.driveFolderError = "";
    renderApi.renderDriveFolderSelection();
    try {
      const [foldersResult, selectedResult, syncResult] = await Promise.allSettled([api.getDriveFolders(), api.getSelectedDriveFolder(), api.getDriveSyncStatus()]);
      if (foldersResult.status !== "fulfilled") throw foldersResult.reason || new Error("Unable to load Drive folders");
      const foldersResponse = foldersResult.value || {};
      const selectedResponse = selectedResult.status === "fulfilled" ? (selectedResult.value || {}) : null;
      const syncResponse = syncResult.status === "fulfilled" ? syncResult.value : null;
      appState.availableDriveFolders = normalizeDriveFolderOptions([...(Array.isArray(foldersResponse?.folders) ? foldersResponse.folders : []), ...(selectedResponse?.folder ? [selectedResponse.folder] : []), ...(appState.selectedDriveFolder?.id ? [appState.selectedDriveFolder] : [])]);
      if (selectedResponse) {
        appState.selectedDriveFolder = selectedResponse.folder || null;
        stateApi.applySelectedDriveFolderSettings(appState.selectedDriveFolder);
      }
      if (syncResponse) appState.driveSyncState = normalizeDriveSyncStatus(syncResponse);
      else if (selectedResponse?.sync) appState.driveSyncState = normalizeDriveSyncStatus(selectedResponse.sync);
      return { folders: appState.availableDriveFolders, selectedFolder: appState.selectedDriveFolder };
    } catch (error) {
      appState.driveFolderError = error.message || "Unable to load Drive folders";
      appState.availableDriveFolders = normalizeDriveFolderOptions([...appState.availableDriveFolders, ...(appState.selectedDriveFolder?.id ? [appState.selectedDriveFolder] : [])]);
      if (!silent) app.showToast(appState.driveFolderError, "warn");
      return { folders: appState.availableDriveFolders, selectedFolder: appState.selectedDriveFolder };
    } finally {
      appState.driveFoldersLoading = false;
      renderApi.syncDriveUI();
      renderApi.renderDriveFolderSelection();
    }
  }

  async function handleDriveFolderSelect(selectEl) {
    const folderId = selectEl?.value || "";
    if (appState.driveSyncState.status === "syncing") return app.showToast("Wait for the current Drive sync to finish before changing folders", "warn");
    if (!folderId) return renderApi.renderDriveFolderSelection();
    const folder = appState.availableDriveFolders.find((item) => item.id === folderId);
    if (!folder) return app.showToast("Selected Drive folder was not found in the current list", "warn");
    if (selectEl) selectEl.disabled = true;
    try {
      const response = await api.saveSelectedDriveFolder(folder.id, folder.name, appState.driveCameraLocation || null, appState.driveSyncLimit);
      appState.selectedDriveFolder = response?.folder || folder;
      stateApi.applySelectedDriveFolderSettings(appState.selectedDriveFolder);
      appState.driveSyncState = normalizeDriveSyncStatus(response?.sync || null);
      appState.driveFolderError = "";
      renderApi.setDriveManualSelectionFeedback(null);
      renderApi.syncDriveUI();
      renderApi.renderDriveFolderSelection();
      app.showToast(`Selected Drive folder: ${folder.name}`, "success");
    } catch (error) {
      appState.driveFolderError = error.message || "Unable to save Drive folder selection";
      renderApi.renderDriveFolderSelection();
      app.showToast(appState.driveFolderError, "warn");
    } finally {
      if (selectEl) selectEl.disabled = false;
    }
  }

  return {
    handleDriveFolderSelect,
    hydrateDriveFolderSelection,
    loadSelectedDriveFolderState
  };
}
