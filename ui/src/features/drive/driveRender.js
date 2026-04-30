/** Drive feature rendering for badges, folder controls, and source summaries. */
import { appState } from "../../state/appState.js";
import { formatNumber, formatTimestampLabel } from "../../utils/format.js";
import {
  formatDriveFolderOptionLabel,
  formatDriveSyncLimitLabel,
  normalizeDriveFolderOptions
} from "../../utils/helpers.js";

export function createDriveRender(app, stateApi, utilsApi) {
  function renderDriveManualSelectionFeedback() {
    const feedbackEl = document.getElementById("drive-folder-manual-feedback");
    if (!feedbackEl) return;
    const message = appState.driveManualSelectionFeedback?.message || utilsApi.getDriveManualSelectionHint();
    const tone = appState.driveManualSelectionFeedback?.tone || "muted";
    feedbackEl.textContent = message;
    feedbackEl.style.color = tone === "success" ? "#166534" : tone === "error" ? "#B42318" : "var(--muted)";
  }

  function setDriveManualSelectionFeedback(message, tone = "muted") {
    appState.driveManualSelectionFeedback = message ? { message, tone } : null;
    renderDriveManualSelectionFeedback();
  }

  function syncDriveSelectionControls() {
    const locationEl = document.getElementById("drive-camera-location-select");
    const limitEl = document.getElementById("drive-sync-limit-select");
    const disabled = appState.driveSyncState.status === "syncing" || !appState.googleAuthActive || !appState.driveConnected;
    if (locationEl) {
      locationEl.value = appState.driveCameraLocation || "";
      locationEl.disabled = disabled;
    }
    if (limitEl) {
      limitEl.value = appState.driveSyncLimit ? String(appState.driveSyncLimit) : "";
      limitEl.disabled = disabled;
    }
  }

  function syncDriveManualSelectionState() {
    const inputEl = document.getElementById("drive-folder-manual-input");
    const buttonEl = document.getElementById("drive-folder-manual-btn");
    const interactive = appState.googleAuthActive && appState.driveConnected && appState.driveSyncState.status !== "syncing" && !appState.driveManualSelectionPending;
    const hasValue = Boolean(String(inputEl?.value || "").trim());
    if (inputEl) {
      inputEl.disabled = !interactive;
      inputEl.placeholder = interactive ? "https://drive.google.com/drive/folders/... or raw folder ID" : "Connect Google Drive to paste a folder URL or ID";
    }
    if (buttonEl) buttonEl.disabled = !interactive || !hasValue;
    renderDriveManualSelectionFeedback();
  }

  function setDriveFolderSelectOptions(selectEl, folders, selectedId) {
    if (!selectEl) return;
    const normalizedFolders = normalizeDriveFolderOptions(folders);
    if (!appState.googleAuthActive) {
      selectEl.innerHTML = `<option value="">Sign in with Google first</option>`;
      selectEl.disabled = true;
      return;
    }
    if (!appState.driveConnected) {
      selectEl.innerHTML = `<option value="">Confirm Google Drive first</option>`;
      selectEl.disabled = true;
      return;
    }
    if (appState.driveFoldersLoading) {
      selectEl.innerHTML = `<option value="">Loading Drive folders…</option>`;
      selectEl.disabled = true;
      return;
    }
    if (!normalizedFolders.length) {
      selectEl.innerHTML = `<option value="">${appState.driveFolderError ? "Drive folders unavailable" : "No Drive folders found"}</option>`;
      selectEl.disabled = true;
      return;
    }
    selectEl.disabled = appState.driveSyncState.status === "syncing";
    selectEl.innerHTML = [`<option value="">Select a Google Drive folder</option>`, ...normalizedFolders.map((folder) => `<option value="${folder.id}"${folder.id === selectedId ? " selected" : ""}>${formatDriveFolderOptionLabel(folder)}</option>`)].join("");
    if (selectedId) selectEl.value = selectedId;
  }

  function updatePipelineSourceSummary() {
    const title = document.getElementById("pipeline-source-name");
    const sub = document.getElementById("pipeline-source-sub");
    if (!title || !sub) return;
    if (appState.uploadTab !== "drive") {
      title.textContent = "Local staging";
      sub.textContent = "Current local-only pipeline flow remains available";
      return;
    }

    if (!appState.selectedDriveFolder?.name) {
      title.textContent = "Google Drive: no folder selected";
      sub.textContent = appState.driveConnected ? "Select a folder on the Upload page before syncing or running the pipeline" : appState.googleAuthActive ? "Confirm Google Drive to run from a backend-selected folder" : "Connect Google Drive to run from a selected folder";
      return;
    }

    title.textContent = `Google Drive: ${appState.selectedDriveFolder.name}`;
    if (appState.driveSyncState.status === "syncing") sub.textContent = `Syncing ${formatNumber(appState.driveSyncState.downloaded_count)} of ${formatNumber(appState.driveSyncState.discovered_count || 0)} image(s) into backend staging`;
    else if (stateApi.isDriveSourceReady()) sub.textContent = `Source ready · ${formatNumber(appState.driveSyncState.downloaded_count || appState.driveSyncState.discovered_count)} staged image(s)${appState.selectedDriveFolder.id ? ` · ID ${appState.selectedDriveFolder.id}` : ""}`;
    else if (appState.driveSyncState.status === "failed") sub.textContent = appState.driveSyncState.error || "The last Drive sync failed. Run Pipeline can retry backend staging, or you can sync again first.";
    else sub.textContent = `Selected Drive folder${appState.selectedDriveFolder.id ? ` · ID ${appState.selectedDriveFolder.id}` : ""} · Run Pipeline will fetch it on the backend if needed`;
  }

  function renderDriveFolderSelection() {
    const selectEl = document.getElementById("drive-folder-select");
    const helperEl = document.getElementById("drive-folder-helper");
    const selectedNameEl = document.getElementById("drive-folder-selected-name");
    const selectedMetaEl = document.getElementById("drive-folder-selected-meta");
    const refreshBtn = document.getElementById("drive-folder-refresh-btn");

    setDriveFolderSelectOptions(selectEl, appState.availableDriveFolders, appState.selectedDriveFolder?.id || "");
    syncDriveSelectionControls();
    if (refreshBtn) refreshBtn.disabled = !appState.driveConnected || appState.driveFoldersLoading || appState.driveSyncState.status === "syncing";
    if (helperEl) helperEl.textContent = !appState.googleAuthActive ? (appState.selectedDriveFolder?.name ? "A backend-selected folder is saved, but Google auth is inactive. Sign in again to load folders." : "Connect Google Drive to load available folders.") : !appState.driveConnected ? (appState.selectedDriveFolder?.name ? "A backend-selected folder is saved. Confirm this Drive connection to use it." : "Confirm the Google Drive connection to load available folders.") : appState.driveSyncState.status === "syncing" ? `Syncing ${formatNumber(appState.driveSyncState.downloaded_count)} of ${formatNumber(appState.driveSyncState.discovered_count || 0)} image(s) from ${appState.selectedDriveFolder?.name || "the selected folder"}...` : appState.driveFoldersLoading ? "Loading folders from Google Drive…" : appState.driveFolderError || (stateApi.isDriveSourceReady() ? `Source ready. ${formatNumber(appState.driveSyncState.downloaded_count || appState.driveSyncState.discovered_count)} image(s) are staged on the backend.` : appState.selectedDriveFolder?.name ? "This folder is saved in the backend. Sync it here to prepare staging, then run the pipeline from the Run Model page." : "Choose the Drive folder to prepare as the backend source.");
    if (selectedNameEl) selectedNameEl.textContent = appState.selectedDriveFolder?.name || "No folder selected";
    if (selectedMetaEl) selectedMetaEl.textContent = !appState.googleAuthActive ? (appState.selectedDriveFolder?.id ? `Stored backend selection · Folder ID: ${appState.selectedDriveFolder.id}` : "Manual upload mode still works without Drive.") : !appState.driveConnected ? (appState.selectedDriveFolder?.id ? `Stored backend selection · Folder ID: ${appState.selectedDriveFolder.id}` : "Confirm this Drive connection to enable folder staging.") : appState.driveSyncState.status === "syncing" ? `${formatNumber(appState.driveSyncState.downloaded_count)} of ${formatNumber(appState.driveSyncState.discovered_count || 0)} files downloading into ${appState.driveSyncState.staging_dir || "data/staging"} · ${formatDriveSyncLimitLabel(appState.driveSyncLimit)}` : stateApi.isDriveSourceReady() ? `${formatNumber(appState.driveSyncState.downloaded_count || appState.driveSyncState.discovered_count)} staged files · ${appState.driveCameraLocation || "Using folder name for location"} · ${formatDriveSyncLimitLabel(appState.driveSyncLimit)}` : appState.selectedDriveFolder?.id ? `${appState.driveCameraLocation || "Using folder name for location"} · ${formatDriveSyncLimitLabel(appState.driveSyncLimit)} · Folder ID: ${appState.selectedDriveFolder.id}` : appState.driveFolderError ? "Folder selection is unavailable until the backend Drive auth flow is active." : "Select a folder in this panel, then use the Run Model page to execute the pipeline.";
    syncDriveManualSelectionState();
    updatePipelineSourceSummary();
  }

  function syncDriveUI() {
    const driveProfile = appState.currentDriveProfile || app.features.auth.resolveDriveProfileFromBackend();
    const driveEmail = appState.googleAuthUser?.email || appState.signedInUser?.email || driveProfile.driveEmail;
    const syncedCount = appState.driveSyncState.downloaded_count || appState.driveSyncState.discovered_count || 0;
    const totalCount = appState.driveSyncState.discovered_count || syncedCount;
    const appliedLimitLabel = formatDriveSyncLimitLabel(appState.selectedDriveFolder?.max_files ?? appState.driveSyncLimit);
    document.getElementById("drive-badge")?.classList.toggle("connected", appState.driveConnected);
    document.getElementById("drive-badge")?.classList.toggle("disconnected", !appState.driveConnected);
    document.getElementById("drive-dot")?.classList.toggle("on", appState.driveConnected);
    document.getElementById("drive-dot")?.classList.toggle("off", !appState.driveConnected);
    const text = document.getElementById("drive-text");
    if (text) text.textContent = appState.driveConnected ? "Google Drive Connected" : appState.googleAuthActive ? "Confirm Google Drive" : "Connect Google Drive";
    document.getElementById("export-disconnected-banner")?.style.setProperty("display", appState.driveConnected ? "none" : "flex");
    document.getElementById("export-drive-content")?.style.setProperty("opacity", appState.driveConnected ? "1" : "0.65");
    const syncTitle = document.getElementById("drive-sync-banner-title");
    const syncSub = document.getElementById("drive-sync-banner-sub");
    if (syncTitle) syncTitle.textContent = appState.driveConnected ? `Connected — ${driveProfile.driveName}` : appState.googleAuthActive ? "Google account connected" : "Google Drive not connected";
    if (syncSub) syncSub.textContent = appState.driveConnected ? `${driveEmail} · Select a folder and sync settings below` : appState.selectedDriveFolder?.name ? (appState.googleAuthActive ? "Confirm this Drive connection to use the saved folder." : "Sign in with Google again to use the saved folder.") : appState.googleAuthActive ? `${driveEmail} · Confirm this Drive connection to enable folder staging` : "Sign in with Google to sync image folders. Manual mode still works.";
    const queueCount = document.getElementById("drive-sync-queue-count");
    if (queueCount) queueCount.textContent = appState.driveSyncState.status === "syncing" || totalCount ? `${formatNumber(syncedCount)} / ${formatNumber(totalCount || 0)} staged` : appState.selectedDriveFolder?.name ? appliedLimitLabel : "Awaiting folder sync";
    const lastSyncTitle = document.getElementById("drive-last-sync-title");
    const lastSyncMeta = document.getElementById("drive-last-sync-meta");
    if (lastSyncTitle) lastSyncTitle.textContent = appState.driveSyncState.status === "completed" && appState.driveSyncState.finished_at ? `Last sync completed ${formatTimestampLabel(appState.driveSyncState.finished_at)}` : appState.driveSyncState.status === "failed" ? "Last sync failed" : appState.driveSyncState.status === "syncing" ? "Sync in progress" : "No completed Drive sync yet";
    if (lastSyncMeta) lastSyncMeta.textContent = appState.driveSyncState.status === "completed" ? `${formatNumber(syncedCount)} image(s) staged on the backend · ${appliedLimitLabel}${appState.driveSyncState.drive_index_path ? ` · ${appState.driveSyncState.drive_index_path}` : ""}` : appState.driveSyncState.status === "failed" ? appState.driveSyncState.error || "Retry sync to prepare this folder." : appState.driveSyncState.last_sync_message || "Sync results will appear here after the first run.";
    updatePipelineSourceSummary();
  }

  return {
    renderDriveFolderSelection,
    renderDriveManualSelectionFeedback,
    setDriveManualSelectionFeedback,
    syncDriveSelectionControls,
    syncDriveManualSelectionState,
    syncDriveUI,
    updatePipelineSourceSummary
  };
}
