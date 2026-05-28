/** Drive feature text and interaction helpers used by render and events. */
import { appState, DRIVE_MANUAL_FOLDER_HINT } from "../../state/appState.js";
import { formatNumber } from "../../utils/format.js";

export function createDriveUtils(stateApi) {
  function getDriveRunIdleNote() {
    if (!appState.googleAuthActive) return "Connect Google Drive to sync a Drive folder. Manual Upload still works separately.";
    if (!appState.driveConnected) return "Confirm the Google Drive connection to use the Drive-backed flow.";
    if (!appState.selectedDriveFolder?.id) return "Select a Google Drive folder on this page before syncing.";
    if (appState.driveSyncState.status === "syncing") {
      const target = Number(appState.driveSyncState.requested_total || appState.driveSyncState.discovered_count || 0);
      return target > 0 ? `Syncing ${formatNumber(target)} files` : "Syncing images...";
    }
    if (appState.driveSyncState.status === "failed") return appState.driveSyncState.error || "The last Drive sync failed. Run Pipeline will retry backend staging, or you can sync again first.";
    if (stateApi.isDriveSourceReady()) return `${formatNumber(appState.driveSyncState.downloaded_count || appState.driveSyncState.discovered_count)} files ready for processing`;
    return "Run Pipeline will fetch and stage the selected Drive folder on the backend server. Sync is optional if you want to pre-stage the cache first.";
  }

  function getDriveManualSelectionHint() {
    if (!appState.googleAuthActive || !appState.driveConnected || appState.driveSyncState.status === "syncing") return "";
    return DRIVE_MANUAL_FOLDER_HINT;
  }

  return {
    getDriveManualSelectionHint,
    getDriveRunIdleNote
  };
}
