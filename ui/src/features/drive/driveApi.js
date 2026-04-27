/** Drive feature API wrappers around the shared backend client. */
import {
  getDriveFolders,
  getDriveStatus,
  getDriveSyncStatus,
  getSelectedDriveFolder,
  saveSelectedDriveFolder,
  syncSelectedDriveFolder
} from "../../services/api.js";

export function createDriveApi() {
  return {
    getDriveFolders,
    getDriveStatus,
    getDriveSyncStatus,
    getSelectedDriveFolder,
    saveSelectedDriveFolder,
    syncSelectedDriveFolder
  };
}
