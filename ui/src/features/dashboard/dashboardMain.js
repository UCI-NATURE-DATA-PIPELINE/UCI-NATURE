/** Dashboard feature entry that loads and renders summary metrics for the homepage. */
import { createDashboardApi } from "./dashboardApi.js";
import { createDashboardCharts } from "./dashboardCharts.js";
import { createDashboardRender } from "./dashboardRender.js";

export function createDashboardFeature(app) {
  const api = createDashboardApi();
  const chartsApi = createDashboardCharts();
  const renderApi = createDashboardRender(app, chartsApi);

  async function loadDashboardData() {
    try {
      const [summary, exportSummary] = await Promise.all([
        api.getDashboardSummary(),
        api.startExportRequest().catch(() => null)
      ]);
      if (exportSummary) app.state.exportData = exportSummary;
      renderApi.applyDashboardSummary(summary, app.state.validationData, app.state.exportData);
      app.state.pageLoadState.dashboard = true;
    } catch (error) {
      renderApi.applyDashboardSummary(null, app.state.validationData, app.state.exportData);
      app.showToast(error.message || "Unable to load dashboard summary", "warn");
    }
  }

  return {
    ...renderApi,
    loadDashboardData
  };
}
