/** Statistics rendering for summary counters and chart fallback states. */
export function createStatisticsRender(chartsApi) {
  function applyStatisticsSummary(speciesCanvas, timelineCanvas, data) {
    document.getElementById("stat-total-detections").textContent = data.total_detections ?? "0";
    document.getElementById("stat-species-count").textContent = data.species_count ?? "0";
    document.getElementById("stat-cameras-count").textContent = data.cameras_count ?? "0";

    if (!data.species_labels?.length) {
      speciesCanvas.parentElement.innerHTML = "<p>No data available</p>";
      return;
    }

    chartsApi.renderCharts(speciesCanvas, timelineCanvas, data);
  }

  return {
    applyStatisticsSummary
  };
}
