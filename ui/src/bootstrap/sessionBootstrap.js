/** App bootstrap helper for restoring auth, Drive, and page state from the backend. */
import { DEV_MODE, DEV_USER } from "../config/runtime.js";
import { getCurrentUser, getDriveStatus, getGoogleAuthStatus, loginUser } from "../services/api.js";

async function establishDevBackendSession(app, showPage, project) {
  try {
    const response = await loginUser(DEV_USER.email, project);
    const sessionToken = String(response?.access_token || "").trim();
    if (!sessionToken) throw new Error("The backend did not return a local dev session token.");

    localStorage.setItem("token", sessionToken);
    app.state.signedInUser = {
      name: DEV_USER.name,
      email: response?.user?.email || DEV_USER.email,
      project: response?.user?.project || project
    };
    console.log("DEV_MODE backend session ready");
    if (typeof app.refreshBackendHealth === "function") {
      await app.refreshBackendHealth({ silent: true });
    }
    await showPage(app.state.currentPage || "dashboard");
    app.showToast("Local dev mode active. Backend session connected.", "success");
  } catch (error) {
    localStorage.removeItem("token");
    console.warn("Dev login failed. Continuing without backend session.", error);
    app.showToast(
      "Local dev mode active without backend session. Start the backend to enable API actions.",
      "warn"
    );
  }
}

async function bootstrapDevModeSession(app, showPage) {
  const project = app.state.selectedProject || "uci";
  console.log("DEV_MODE auth bypass enabled");
  localStorage.removeItem("token");

  app.state.signedInUser = {
    name: DEV_USER.name,
    email: DEV_USER.email,
    project
  };
  app.state.driveConnected = false;
  app.state.googleAuthActive = false;
  app.state.googleAuthUser = null;
  app.state.selectedDriveFolder = null;
  app.state.availableDriveFolders = [];
  app.state.driveFoldersLoading = false;
  app.state.driveFolderError = "";
  app.features.drive.applySelectedDriveFolderSettings(null);
  app.features.drive.applyDriveSyncStatus(null);
  app.features.auth.updateDriveConfirmation();
  app.features.drive.syncDriveUI();
  app.features.drive.renderDriveFolderSelection();
  app.features.auth.enterDashboard();
  app.features.drive.switchUploadTab("manual");
  await showPage("dashboard");
  void establishDevBackendSession(app, showPage, project);
}

export async function bootstrapAppState(app, showPage) {
  const oauthResult = new URLSearchParams(window.location.search).get("google_auth");
  const token = localStorage.getItem("token");

  if (DEV_MODE) {
    try {
      await bootstrapDevModeSession(app, showPage);
    } finally {
      if (oauthResult) app.features.auth.clearOAuthQueryParams();
    }
    return;
  }

  if (!token) {
    app.features.auth.returnToLogin();
    if (oauthResult) app.features.auth.clearOAuthQueryParams();
    return;
  }

  try {
    let user = null;
    try {
      user = await getCurrentUser();
    } catch (error) {
      user = null;
    }
    console.log("User:", user);

    if (!user) {
      console.warn("No backend session available. Returning to login.");
      app.state.driveConnected = false;
      app.state.signedInUser = null;
      app.state.googleAuthActive = false;
      app.state.googleAuthUser = null;
      app.state.selectedDriveFolder = null;
      app.features.drive.applySelectedDriveFolderSettings(null);
      app.features.drive.applyDriveSyncStatus(null);
      localStorage.removeItem("token");
      app.features.auth.updateDriveConfirmation();
      app.features.drive.syncDriveUI();
      app.features.drive.renderDriveFolderSelection();
      app.features.auth.returnToLogin();
      app.features.auth.setLoginStep(2);
      return;
    }

    let googleAuth = { authenticated: false, user: null };
    let driveStatus = { connected: false, drive_name: null, drive_email: null, selected_folder: null };

    const [googleAuthResult, driveStatusResult] = await Promise.allSettled([getGoogleAuthStatus(), getDriveStatus()]);
    if (googleAuthResult.status === "fulfilled") googleAuth = googleAuthResult.value;
    if (driveStatusResult.status === "fulfilled") driveStatus = driveStatusResult.value;

    app.state.signedInUser = user || null;
    if (googleAuth?.authenticated && googleAuth?.user?.email) {
      app.state.signedInUser = { ...(user || {}), email: googleAuth.user.email };
    }
    if (app.state.signedInUser?.project) app.state.selectedProject = app.state.signedInUser.project;

    app.features.auth.applyBackendDriveState(googleAuth, driveStatus);
    app.state.availableDriveFolders = [];
    app.state.driveFoldersLoading = false;
    app.state.driveFolderError = "";
    app.features.auth.updateDriveConfirmation();
    app.features.drive.syncDriveUI();
    app.features.drive.renderDriveFolderSelection();
    await app.features.pipeline.loadPipelineStatus({ silent: true });

    if (app.state.googleAuthActive && app.state.driveConnected) {
      app.features.auth.enterDashboard();
      await app.features.drive.hydrateDriveFolderSelection({ silent: true });
      if (app.state.selectedDriveFolder?.id) await showPage("dashboard");
      else {
        app.features.drive.switchUploadTab("drive");
        await showPage("upload");
      }
      if (oauthResult === "success") app.showToast("Google sign-in successful", "success");
    } else if (app.state.googleAuthActive) {
      app.features.auth.returnToLogin();
      app.features.auth.setLoginStep(3);
      app.features.auth.setDriveModalVisible(true);
      if (oauthResult === "success") app.showToast("Google sign-in successful. Confirm the project drive to continue.", "success");
    } else {
      app.features.auth.enterDashboard();
      await showPage("dashboard");
      if (oauthResult === "error") app.showToast("Google sign-in failed. Local mode is still available.", "warn");
    }
  } catch (error) {
    app.state.driveConnected = false;
    app.state.signedInUser = null;
    app.state.googleAuthActive = false;
    app.state.googleAuthUser = null;
    app.state.selectedDriveFolder = null;
    app.features.drive.applySelectedDriveFolderSettings(null);
    localStorage.removeItem("token");
    app.features.drive.applyDriveSyncStatus(null);
    app.features.auth.updateDriveConfirmation();
    app.features.drive.syncDriveUI();
    app.features.drive.renderDriveFolderSelection();
    app.features.auth.returnToLogin();
    app.features.auth.setLoginStep(2);
  } finally {
    if (oauthResult) app.features.auth.clearOAuthQueryParams();
  }
}
