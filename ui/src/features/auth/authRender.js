/** Auth feature rendering for login steps, Drive confirmation, and screen visibility. */
import { appState } from "../../state/appState.js";

export function createAuthRender(stateApi) {
  function setLoginStep(step) {
    const step1 = document.getElementById("login-step1");
    const step2 = document.getElementById("login-step2");
    const label1 = document.getElementById("lstep-1");
    const label2 = document.getElementById("lstep-2");
    const label3 = document.getElementById("lstep-3");

    if (step1) step1.style.display = step === 1 ? "block" : "none";
    if (step2) step2.style.display = step === 2 || step === 3 ? "block" : "none";
    [label1, label2, label3].forEach((element) => element?.classList.remove("active", "done"));
    if (step === 1) label1?.classList.add("active");
    if (step === 2) {
      label1?.classList.add("done");
      label2?.classList.add("active");
    }
    if (step === 3) {
      label1?.classList.add("done");
      label2?.classList.add("done");
      label3?.classList.add("active");
    }
  }

  function setDriveModalVisible(isVisible) {
    document.getElementById("drive-modal")?.classList.toggle("visible", isVisible);
  }

  function updateDriveConfirmation() {
    appState.currentDriveProfile = stateApi.resolveDriveProfileFromBackend();
    const userEmail =
      appState.googleAuthUser?.email ||
      appState.signedInUser?.email ||
      appState.currentDriveProfile.driveEmail;

    const title = document.getElementById("drive-modal-title");
    const sub = document.getElementById("drive-modal-sub");
    const name = document.getElementById("drive-confirm-name");
    const account = document.getElementById("drive-confirm-account");
    const confirmBtn = document.getElementById("drive-confirm-btn");

    if (title) title.textContent = appState.googleAuthActive ? "Confirm Drive Connection" : "Connect Google Drive";
    if (sub) {
      sub.textContent = appState.googleAuthActive
        ? "We found the following Google Drive. Please confirm this is the correct project drive before continuing."
        : "Sign in with the Google account that can access this project folder. Local mode remains available without Drive.";
    }
    if (name) name.textContent = appState.currentDriveProfile.driveName;
    if (account) {
      account.textContent = appState.googleAuthActive
        ? `${userEmail} · ${appState.currentDriveProfile.projectLabel}`
        : `${appState.currentDriveProfile.projectLabel} · Not signed in`;
    }
    if (confirmBtn) {
      confirmBtn.textContent = appState.googleAuthActive ? "Confirm & Enter Dashboard" : "Sign in with Google first";
      confirmBtn.disabled = !appState.googleAuthActive;
    }
  }

  function enterDashboard() {
    setDriveModalVisible(false);
    document.getElementById("login-screen")?.style.setProperty("display", "none");
    document.getElementById("main-app")?.style.setProperty("display", "flex");
  }

  function returnToLogin() {
    setDriveModalVisible(false);
    document.getElementById("login-screen")?.style.setProperty("display", "flex");
    document.getElementById("main-app")?.style.setProperty("display", "none");
  }

  return {
    enterDashboard,
    returnToLogin,
    setDriveModalVisible,
    setLoginStep,
    updateDriveConfirmation
  };
}
