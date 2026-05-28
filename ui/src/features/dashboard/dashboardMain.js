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
      const [summary, exportSummary, validationData, speciesHistogram, pipelineStatus] = await Promise.all([
        api.getDashboardSummary(),
        api.startExportRequest().catch(() => null),
        app.features.validate.loadValidationData({ showToastOnError: false }).catch(() => null),
        api.getDashboardSpeciesHistogram().catch(() => null),
        app.features.pipeline.loadPipelineStatus({ silent: true })
      ]);
      if (exportSummary) app.state.exportData = exportSummary;
      if (validationData) app.state.validationData = validationData;
      app.state.dashboardSpeciesHistogram = speciesHistogram || null;
      app.state.dashboardSpeciesHistogramSelected = speciesHistogram?.default_park_key || "";
      renderApi.applyDashboardSummary(summary, app.state.validationData, app.state.exportData, pipelineStatus || app.state.pipelineStatus, app.state.dashboardSpeciesHistogram);
      app.state.pageLoadState.dashboard = true;
    } catch (error) {
      app.state.dashboardSpeciesHistogram = null;
      app.state.dashboardSpeciesHistogramSelected = "";
      renderApi.applyDashboardSummary(null, app.state.validationData, app.state.exportData, app.state.pipelineStatus, null);
      app.showToast(error.message || "Unable to load dashboard summary", "warn");
    }
  }

  return {
    ...renderApi,
    loadDashboardData
  };
}
