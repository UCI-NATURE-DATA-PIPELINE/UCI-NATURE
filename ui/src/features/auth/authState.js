/** Auth feature state helpers for project-specific Drive profiles and session state. */
import { normalizeDriveSyncStatus } from "../../utils/helpers.js";
import { appState, driveProfiles, projectLabels } from "../../state/appState.js";

export function createAuthState(app) {
  function getDriveProfile() {
    // Fallback values used only if a future project slug is selected before
    // its profile has been registered in driveProfiles.
    return driveProfiles[appState.selectedProject] || {
      driveName: "UCI Nature Wildlife Drive",
      driveEmail: "",
      projectLabel: projectLabels[appState.selectedProject] || "UCI Nature Wildlife Camera Project"
    };
  }

  function resolveDriveProfileFromBackend(driveStatus = null) {
    const fallbackProfile = getDriveProfile();
    return {
      ...fallbackProfile,
      driveName:
        driveStatus?.drive_name ||
        appState.currentDriveProfile?.driveName ||
        fallbackProfile.driveName,
      driveEmail:
        driveStatus?.drive_email ||
        appState.googleAuthUser?.email ||
        appState.signedInUser?.email ||
        appState.currentDriveProfile?.driveEmail ||
        fallbackProfile.driveEmail
    };
  }

  function applyBackendDriveState(googleAuth = null, driveStatus = null) {
    appState.googleAuthActive = Boolean(googleAuth?.authenticated);
    appState.googleAuthUser = googleAuth?.user || null;
    appState.driveConnected = appState.googleAuthActive && Boolean(driveStatus?.connected);
    appState.selectedDriveFolder = driveStatus?.selected_folder || appState.selectedDriveFolder || null;
    app.features.drive.applySelectedDriveFolderSettings(appState.selectedDriveFolder);
    appState.driveSyncState = normalizeDriveSyncStatus(driveStatus?.sync || appState.driveSyncState);
    appState.currentDriveProfile = resolveDriveProfileFromBackend(driveStatus);
  }

  return {
    applyBackendDriveState,
    getDriveProfile,
    resolveDriveProfileFromBackend
  };
}
