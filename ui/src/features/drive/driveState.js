/** Drive feature state helpers for selection, readiness, and sync progress. */
import { appState } from "../../state/appState.js";
import { normalizeDriveSyncLimitValue, normalizeDriveSyncStatus } from "../../utils/helpers.js";

export function createDriveState() {
  function applySelectedDriveFolderSettings(folder = null) {
    appState.driveCameraLocation = String(folder?.camera_location || "");
    appState.driveSyncLimit = normalizeDriveSyncLimitValue(folder?.max_files);
  }

  function applyDriveSyncStatus(value) {
    appState.driveSyncState = normalizeDriveSyncStatus(value);
    return appState.driveSyncState;
  }

  function isDriveSourceReady() {
    return Boolean(
      appState.driveConnected &&
      appState.selectedDriveFolder?.id &&
      appState.driveSyncState.source_ready &&
      appState.driveSyncState.folder?.id === appState.selectedDriveFolder.id
    );
  }

  function canRunDrivePipeline() {
    return Boolean(
      appState.googleAuthActive &&
      appState.driveConnected &&
      appState.selectedDriveFolder?.id &&
      appState.driveSyncState.status !== "syncing"
    );
  }

  function getDriveSyncStepPercent() {
    const explicitPercent = Number(appState.pipelineStatus?.progress?.percent);
    if (Number.isFinite(explicitPercent) && explicitPercent >= 0) {
      return Math.max(0, Math.min(100, explicitPercent));
    }

    const step = (appState.pipelineStatus?.current_step || "").toLowerCase();
    if (!step) return appState.runningModel ? 8 : 0;
    if (step.includes("create manifest")) return 15;
    if (step.includes("extract metadata (exif)")) return 28;
    if (step.includes("run speciesnet")) return 55;
    if (step.includes("postprocess speciesnet")) return 70;
    if (step.includes("parse ml results")) return 82;
    if (step.includes("extract metadata (merge ml)")) return 90;
    if (step.includes("generate output csvs")) return 96;
    return appState.runningModel ? 12 : 0;
  }

  return {
    applyDriveSyncStatus,
    applySelectedDriveFolderSettings,
    canRunDrivePipeline,
    getDriveSyncStepPercent,
    isDriveSourceReady
  };
}
