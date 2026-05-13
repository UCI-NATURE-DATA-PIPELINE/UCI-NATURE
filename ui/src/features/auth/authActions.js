/** Auth feature actions for login flow, Drive confirmation, and account switching. */
import { appState, createEmptyDriveSyncState } from "../../state/appState.js";

export function createAuthActions(app, api, stateApi, renderApi) {
  function clearOAuthQueryParams() {
    const url = new URL(window.location.href);
    url.searchParams.delete("google_auth");
    window.history.replaceState({}, document.title, url.toString());
  }

  function selectProject(cardEl) {
    document.querySelectorAll(".project-card").forEach((card) => {
      if (!card.classList.contains("disabled")) card.classList.remove("selected");
    });
    cardEl.classList.add("selected");
    // Only one project is configured today (UCI Nature Wildlife Camera
    // Project). Add more mappings here as new projects come online.
    appState.selectedProject = "uci";
    appState.currentDriveProfile = null;
    renderApi.updateDriveConfirmation();
  }

  /**
   * Kicks off the real Google OAuth flow: mint a backend session via
   * /api/auth/login, fetch the Google auth URL from /api/auth/google/start,
   * then redirect the browser.
   */
  async function startGoogleSignIn() {
    const oauthBtn = document.getElementById("oauth-btn");
    const originalText = oauthBtn?.innerHTML;
    renderApi.setLoginStep(3);
    if (oauthBtn) {
      oauthBtn.disabled = true;
      oauthBtn.textContent = "Connecting...";
    }

    appState.currentDriveProfile = stateApi.getDriveProfile();

    try {
      const response = await api.loginUser(appState.currentDriveProfile.driveEmail, appState.selectedProject);
      const sessionToken = String(response?.access_token || "").trim();
      if (sessionToken) localStorage.setItem("token", sessionToken);
      const authUrl = await api.getGoogleAuthStartUrl(sessionToken);

      appState.signedInUser = response?.user || null;
      appState.googleAuthActive = false;
      appState.googleAuthUser = null;
      renderApi.updateDriveConfirmation();

      if (!authUrl) throw new Error("Google OAuth start URL was not returned by the backend");
      window.location.assign(authUrl);
    } catch (error) {
      localStorage.removeItem("token");
      appState.signedInUser = null;
      appState.googleAuthActive = false;
      appState.googleAuthUser = null;
      app.showToast(error.message || "Unable to start Google sign-in", "warn");
      renderApi.setLoginStep(2);
    } finally {
      if (oauthBtn) {
        oauthBtn.innerHTML = originalText;
        oauthBtn.disabled = false;
      }
    }
  }

  async function continueWithoutGoogleDrive() {
    const localBtn = document.getElementById("local-login-btn");
    const originalHtml = localBtn?.innerHTML;
    if (localBtn) {
      localBtn.disabled = true;
      localBtn.textContent = "Opening Manual Upload...";
    }

    try {
      const response = await api.loginUser("", appState.selectedProject);
      const sessionToken = String(response?.access_token || "").trim();
      if (!sessionToken) throw new Error("The backend did not return a session token.");
      localStorage.setItem("token", sessionToken);

      appState.signedInUser = response?.user || { project: appState.selectedProject };
      appState.currentDriveProfile = null;
      appState.googleAuthActive = false;
      appState.googleAuthUser = null;
      appState.driveConnected = false;
      appState.selectedDriveFolder = null;
      appState.availableDriveFolders = [];
      appState.driveFoldersLoading = false;
      appState.driveFolderError = "";
      appState.driveSyncState = createEmptyDriveSyncState();
      appState.driveManualSelectionFeedback = null;
      appState.driveManualSelectionPending = false;
      app.features.drive.stopDriveSyncPolling();
      app.features.drive.applySelectedDriveFolderSettings(null);
      app.features.drive.applyDriveSyncStatus(null);
      app.features.drive.syncDriveUI();
      app.features.drive.renderDriveFolderSelection();
      renderApi.updateDriveConfirmation();
      renderApi.enterDashboard();
      app.features.drive.switchUploadTab("manual");
      await app.showPage("upload");
      app.showToast("Manual Upload is ready. Google Drive is not connected.", "success");
    } catch (error) {
      localStorage.removeItem("token");
      appState.signedInUser = null;
      app.showToast(error.message || "Unable to start a local session", "warn");
    } finally {
      if (localBtn) {
        localBtn.innerHTML = originalHtml;
        localBtn.disabled = false;
      }
    }
  }

  async function confirmDrive() {
    if (!appState.googleAuthActive) {
      app.showToast("Connect Google Drive before confirming Drive", "warn");
      return;
    }

    appState.currentDriveProfile = stateApi.getDriveProfile();
    try {
      const response = await api.connectDrive(
        appState.currentDriveProfile.driveName,
        appState.signedInUser?.email || appState.currentDriveProfile.driveEmail
      );

      appState.driveConnected = appState.googleAuthActive && Boolean(response?.connected);
      appState.currentDriveProfile = stateApi.resolveDriveProfileFromBackend({
        drive_name: response?.drive_name,
        drive_email: response?.drive_email,
        selected_folder: response?.selected_folder
      });
      appState.selectedDriveFolder = response?.selected_folder || appState.selectedDriveFolder;
      app.features.drive.setDriveManualSelectionFeedback(null);
      app.features.drive.syncDriveUI();
      await app.features.drive.hydrateDriveFolderSelection({ silent: true });
      renderApi.enterDashboard();
      app.features.drive.switchUploadTab("drive");
      app.showPage("upload");
      app.showToast("Google Drive connected. Pick a folder to continue.", "success");
    } catch (error) {
      appState.driveConnected = false;
      app.features.drive.syncDriveUI();
      app.showToast(error.message || "Google Drive confirmation failed", "warn");
    }
  }

  async function switchAccount() {
    try {
      await api.logoutGoogleAuth();
    } catch (error) {
      // Allow the UI reset to continue if the backend session has already expired.
    }

    appState.driveConnected = false;
    appState.signedInUser = null;
    appState.currentDriveProfile = null;
    appState.googleAuthActive = false;
    appState.googleAuthUser = null;
    appState.selectedDriveFolder = null;
    app.features.drive.applySelectedDriveFolderSettings(null);
    appState.availableDriveFolders = [];
    appState.driveFoldersLoading = false;
    appState.driveFolderError = "";
    appState.driveSyncState = createEmptyDriveSyncState();
    appState.driveManualSelectionFeedback = null;
    appState.driveManualSelectionPending = false;
    app.features.drive.stopDriveSyncPolling();
    localStorage.removeItem("token");
    renderApi.setDriveModalVisible(false);
    renderApi.setLoginStep(2);
    renderApi.updateDriveConfirmation();
    app.features.drive.syncDriveUI();
    app.features.drive.renderDriveFolderSelection();
  }

  function openDriveModal() {
    if (!appState.googleAuthActive) {
      renderApi.returnToLogin();
      renderApi.setLoginStep(2);
      renderApi.updateDriveConfirmation();
      return;
    }
    renderApi.updateDriveConfirmation();
    renderApi.setDriveModalVisible(true);
  }

  function reconnectDrive() {
    openDriveModal();
  }

  return {
    clearOAuthQueryParams,
    confirmDrive,
    continueWithoutGoogleDrive,
    openDriveModal,
    reconnectDrive,
    selectProject,
    startGoogleSignIn,
    switchAccount
  };
}
