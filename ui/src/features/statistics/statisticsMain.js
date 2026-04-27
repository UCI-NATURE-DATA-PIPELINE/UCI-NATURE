/** Statistics feature entry that loads analytics data and renders charts. */
import { createStatisticsApi } from "./statisticsApi.js";
import { createStatisticsCharts } from "./statisticsCharts.js";
import { createStatisticsRender } from "./statisticsRender.js";

export function createStatisticsFeature(app) {
  const api = createStatisticsApi();
  const chartsApi = createStatisticsCharts(app);
  const renderApi = createStatisticsRender(chartsApi);

  async function loadStatistics() {
    const speciesCanvas = document.getElementById("chart-species");
    const timelineCanvas = document.getElementById("chart-timeline");
    if (!speciesCanvas || !timelineCanvas) return;
    if (speciesCanvas.offsetWidth === 0 || speciesCanvas.offsetHeight === 0) {
      requestAnimationFrame(loadStatistics);
      return;
    }

    try {
      const data = await api.getStatisticsSummary();
      renderApi.applyStatisticsSummary(speciesCanvas, timelineCanvas, data);
    } catch (error) {
      speciesCanvas.parentElement.innerHTML = "<p>Failed to load statistics</p>";
    }
  }

  return {
    loadStatistics
  };
}
