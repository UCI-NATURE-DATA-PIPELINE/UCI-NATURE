/** Browser-native entrypoint that initializes the shell, features, and session state. */
import { appState } from "./state/appState.js";
import { buildDatePickers } from "./components/common/datePickers.js";
import { openConfirmModal } from "./components/common/confirmModal.js";
import { showToast } from "./components/common/toast.js";
import { createBackendStatus } from "./components/layout/backendStatus.js";
import { bindLayoutNavigation } from "./components/layout/navigation.js";
import { registerFeatures } from "./bootstrap/featureRegistry.js";
import { loadFeatureMarkup } from "./bootstrap/markupLoader.js";
import { createPageController } from "./bootstrap/pageController.js";
import { bootstrapAppState } from "./bootstrap/sessionBootstrap.js";
import { bindGlobals } from "./bootstrap/windowBindings.js";
import { DEV_MODE } from "./config/runtime.js";
import { getBackendHealth } from "./services/api.js";

const app = {
  state: appState,
  features: {},
  openConfirmModal,
  showToast
};

function setBootSplashStatus(title, subtitle, { showRetry = false, error = false } = {}) {
  const root = document.getElementById("app-boot");
  const titleEl = document.getElementById("app-boot-title");
  const subEl = document.getElementById("app-boot-sub");
  const retryEl = document.getElementById("app-boot-retry");
  if (root) root.classList.toggle("error", Boolean(error));
  if (titleEl && title) titleEl.textContent = title;
  if (subEl && subtitle) subEl.textContent = subtitle;
  if (retryEl) retryEl.hidden = !showRetry;
}

function hideBootSplash() {
  const root = document.getElementById("app-boot");
  if (root) root.hidden = true;
}

function revealAuthShells() {
  // The boot splash hides auth-root + main-app while we run health/auth checks.
  // Bootstrap will toggle one of them visible based on the result; here we just
  // make sure their inline display:none placeholders aren't blocking that.
  const authRoot = document.getElementById("auth-root");
  if (authRoot) authRoot.style.display = "";
}

async function initializeApp() {
  console.log("App start");
  if (DEV_MODE) console.log("Local dev mode enabled");
  setBootSplashStatus("Starting Wildlife Research…", "Loading interface modules.");

  // Register features + window bindings BEFORE awaiting markup so that any
  // inline onclick="startGoogleSignIn()" etc. resolves the moment the markup
  // appears. Otherwise an early click during partial fetch produces
  // "startGoogleSignIn is not defined" in the console.
  const backendStatusApi = createBackendStatus();
  registerFeatures(app);
  const { showPage } = createPageController(app);
  bindGlobals(app, showPage);
  bindLayoutNavigation({ showPage });

  await loadFeatureMarkup();
  console.log("Markup loaded");
  app.applyBackendHealthStatus = (health) => {
    backendStatusApi.applyBackendHealthStatus(health);
    // Keep the Upload page's backend banners / Process buttons in sync with the
    // header status pill so users see one consistent connectivity message.
    app.features.drive?.refreshManualUpload?.();
    const driveOfflineBanner = document.getElementById("drive-backend-banner");
    if (driveOfflineBanner) {
      driveOfflineBanner.hidden = Boolean(health?.connected);
    }
  };
  app.refreshBackendHealth = async ({ silent = false } = {}) => {
    try {
      const health = await getBackendHealth();
      app.applyBackendHealthStatus({
        ...health,
        connected: true
      });
      return {
        ...health,
        connected: true
      };
    } catch (error) {
      app.applyBackendHealthStatus(null);
      if (!silent) app.showToast(error.message || "Backend offline", "warn");
      return null;
    }
  };
  app.features.auth.setLoginStep(1);
  app.features.auth.updateDriveConfirmation();
  app.features.review.renderReviewQueue();
  app.features.review.renderReviewViewer();
  app.features.validate.renderAffectedImages(null);
  app.features.validate.renderUnprocessedImages(null);
  app.features.export.syncExportFilenamePreview();
  buildDatePickers();
  app.features.dashboard.applyDashboardSummary(null);
  app.features.validate.applyValidationData(null);
  app.features.export.applyExportData(null, null);
  app.features.pipeline.applyPipelineStatus(null);
  app.features.drive.syncDriveUI();
  app.features.drive.renderDriveFolderSelection();
  app.features.drive.initializeManualUpload();

  setBootSplashStatus("Checking backend…", "Looking for the API at 127.0.0.1:8000.");
  const healthResult = await app.refreshBackendHealth({ silent: true });
  if (healthResult) {
    setBootSplashStatus("Loading your session…", "Restoring your sign-in state.");
  } else {
    // Don't trap the user on a spinner — fall through to login/dashboard so
    // they can see the offline banner and retry from the header.
    setBootSplashStatus(
      "Backend not connected",
      "We'll continue offline. Start the backend on 127.0.0.1:8000 to enable processing.",
      { error: true }
    );
  }

  revealAuthShells();
  await bootstrapAppState(app, showPage);
  hideBootSplash();
}

document.addEventListener("DOMContentLoaded", () => {
  void initializeApp().catch((error) => {
    console.error("App initialization failed:", error);
    // Never trap the user on the boot spinner if something throws — surface
    // the error in the splash and reveal the auth shell so login is reachable.
    setBootSplashStatus(
      "App failed to start",
      error?.message || "Unexpected error. Reload the page or contact support.",
      { error: true, showRetry: true }
    );
    revealAuthShells();
    const retryEl = document.getElementById("app-boot-retry");
    if (retryEl) retryEl.onclick = () => window.location.reload();
  });
});
