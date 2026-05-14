/** Statistics rendering for summary counters and chart fallback states. */
export function createStatisticsRender(chartsApi) {
  function applyStatisticsSummary(speciesCanvas, timelineCanvas, data) {
    document.getElementById("stat-total-detections").textContent = data.total_detections ?? "0";
    document.getElementById("stat-species-count").textContent = data.species_count ?? "0";
    document.getElementById("stat-cameras-count").textContent = data.cameras_count ?? "0";
  
    const speciesParent = speciesCanvas.parentElement;
    let emptyMsg = speciesParent.querySelector(".stats-empty-msg");
  
    if (!data.species_labels?.length) {
      speciesCanvas.style.display = "none";
      if (!emptyMsg) {
        emptyMsg = document.createElement("p");
        emptyMsg.className = "stats-empty-msg";
        emptyMsg.textContent = "No data available";
        speciesParent.appendChild(emptyMsg);
      }
      return;
    }
  
    speciesCanvas.style.display = "block";
    if (emptyMsg) emptyMsg.remove();
    chartsApi.renderCharts(speciesCanvas, timelineCanvas, data);
  }

  return {
    applyStatisticsSummary
  };
}
