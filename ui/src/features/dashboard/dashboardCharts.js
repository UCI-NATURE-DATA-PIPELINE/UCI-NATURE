/** Dashboard chart helpers for the species detection donut graphic. */
export function createDashboardCharts() {
  function destroyHistogramChart(app) {
    if (app.state.charts.dashboardSpeciesHistogram) {
      app.state.charts.dashboardSpeciesHistogram.destroy();
      app.state.charts.dashboardSpeciesHistogram = null;
    }
  }

  function buildSpeciesDonut(data) {
    const svg = document.getElementById("species-svg");
    if (!svg) return;

    svg.querySelectorAll("circle[data-segment='true']").forEach((node) => node.remove());
    const radius = 52;
    const circumference = 2 * Math.PI * radius;
    let offset = 0;

    data.forEach((item) => {
      if (!item.value) return;
      const segment = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      const dash = (item.value / 100) * circumference;
      segment.setAttribute("cx", "65");
      segment.setAttribute("cy", "65");
      segment.setAttribute("r", String(radius));
      segment.setAttribute("fill", "none");
      segment.setAttribute("stroke", item.color);
      segment.setAttribute("stroke-width", "14");
      segment.setAttribute("stroke-dasharray", `${dash} ${circumference}`);
      segment.setAttribute("stroke-dashoffset", String(-offset + 82));
      segment.setAttribute("stroke-linecap", "round");
      segment.setAttribute("data-segment", "true");
      svg.appendChild(segment);
      offset += dash;
    });
  }

  function buildSpeciesHistogram(app, canvas, data) {
    destroyHistogramChart(app);
    if (!canvas || !data?.labels?.length || !data?.values?.length) {
      return null;
    }

    app.state.charts.dashboardSpeciesHistogram = new Chart(canvas, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [{
          label: data.label || "Detections",
          data: data.values,
          backgroundColor: "#0064A4",
          borderRadius: 8,
          borderSkipped: false
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: "y",
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label(context) {
                const value = Number(context.parsed?.x || 0);
                return `${value.toLocaleString()} detection${value === 1 ? "" : "s"}`;
              }
            }
          }
        },
        scales: {
          x: {
            beginAtZero: true,
            ticks: {
              precision: 0,
              color: "#718096"
            },
            grid: {
              color: "rgba(226,232,240,.9)"
            }
          },
          y: {
            ticks: {
              color: "#2D3748",
              font: {
                size: 12,
                weight: "600"
              }
            },
            grid: {
              display: false
            }
          }
        }
      }
    });

    return app.state.charts.dashboardSpeciesHistogram;
  }

  return {
    buildSpeciesDonut,
    buildSpeciesHistogram
  };
}
