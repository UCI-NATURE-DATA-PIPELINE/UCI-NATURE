/** Statistics chart helpers for creating and replacing Chart.js instances. */
export function createStatisticsCharts(app) {
  function destroyCharts() {
    if (app.state.charts.species) app.state.charts.species.destroy();
    if (app.state.charts.timeline) app.state.charts.timeline.destroy();
  }

  function renderCharts(speciesCanvas, timelineCanvas, data) {
    destroyCharts();
    app.state.charts.species = new Chart(speciesCanvas, {
      type: "bar",
      data: { labels: data.species_labels, datasets: [{ label: "Detections", data: data.species_values, backgroundColor: "#0064A4" }] },
      options: { responsive: true, maintainAspectRatio: false }
    });
    app.state.charts.timeline = new Chart(timelineCanvas, {
      type: "line",
      data: { labels: data.timeline_labels, datasets: [{ label: "Detections", data: data.timeline_values, borderColor: "#7AB800", fill: true }] },
      options: { responsive: true, maintainAspectRatio: false }
    });
  }

  return {
    renderCharts
  };
}
