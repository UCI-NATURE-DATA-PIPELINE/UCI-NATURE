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

async function initializeApp() {
  console.log("App start");
  if (DEV_MODE) console.log("Local dev mode enabled");
  await loadFeatureMarkup();
  console.log("Markup loaded");
  const backendStatusApi = createBackendStatus();
  registerFeatures(app);
  const { showPage } = createPageController(app);
  bindGlobals(app, showPage);
  bindLayoutNavigation({ showPage });
  app.applyBackendHealthStatus = backendStatusApi.applyBackendHealthStatus;
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
  const bootstrapPromise = bootstrapAppState(app, showPage);
  void app.refreshBackendHealth({ silent: true });
  await bootstrapPromise;
}

document.addEventListener("DOMContentLoaded", () => {
  void initializeApp().catch((error) => {
    console.error("App initialization failed:", error);
  });
});
