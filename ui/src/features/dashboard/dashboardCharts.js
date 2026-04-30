/** Dashboard chart helpers for the species detection donut graphic. */
export function createDashboardCharts() {
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

  return {
    buildSpeciesDonut
  };
}
