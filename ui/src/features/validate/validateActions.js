/** Validate actions for backend refresh, panel toggles, and preview updates. */
import { setText } from "../../utils/dom.js";

export function createValidateActions(app, api, renderApi) {
  async function loadValidationData({ showToastOnError = false } = {}) {
    try {
      const data = await api.getValidationIssues();
      renderApi.applyValidationData(data);
      app.state.pageLoadState.validate = true;
      return data;
    } catch (error) {
      renderApi.applyValidationData(null);
      if (showToastOnError) app.showToast(error.message || "Unable to load validation issues", "warn");
      return null;
    }
  }

  async function runValidation() {
    const data = await loadValidationData({ showToastOnError: true });
    if (!data) return;
    if (app.state.dashboardSummary) {
      app.features.dashboard.applyDashboardSummary(app.state.dashboardSummary, data, app.state.exportData);
    }
    if (app.state.currentPage === "export") {
      app.features.export.applyExportData(app.state.exportData, data);
    }
    app.showToast("Validation refreshed from current output artifacts", "success");
  }

  return {
    loadValidationData,
    runValidation,
    toggleAffectedPanel: () => document.getElementById("affected-panel")?.classList.toggle("open"),
    toggleUnprocPanel: () => document.getElementById("unproc-panel")?.classList.toggle("open"),
    updateTimePreview: (value) => setText("time-preview-after", `After: 2024-03-10 ${String(1 + Number(value || 0)).padStart(2, "0")}:30:00`)
  };
}
