/** Dashboard rendering for summary cards, export chips, and activity lists. */
import { setText } from "../../utils/dom.js";
import { escapeHtml, formatNumber, formatPercent, getPercent } from "../../utils/format.js";

export function createDashboardRender(app, chartsApi) {
  function animateValue(element, start, end, duration, format) {
    const startTime = performance.now();
    function update(now) {
      const progress = Math.min((now - startTime) / duration, 1);
      const value = Math.floor(start + (end - start) * progress);
      element.textContent = format === "comma" ? value.toLocaleString() : String(value);
      if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
  }

  function setDashboardStat(id, nextValue, format = "comma") {
    const element = document.getElementById(id);
    if (!element) return;
    const previousValue = Number((element.textContent || "0").replaceAll(",", "") || 0);
    animateValue(element, Number.isFinite(previousValue) ? previousValue : 0, Number(nextValue || 0), 500, format);
  }

  function renderDashboardCameraChips(files = []) {
    const container = document.getElementById("dashboard-camera-chip-list");
    if (!container) return;
    container.innerHTML = files.length
      ? files.map((file) => `
          <span style="display:inline-flex;align-items:center;gap:5px;padding:3px 9px;background:#F0FFF4;border:1.5px solid #9AE6B4;border-radius:20px;font-size:11.5px;font-weight:600;color:#276749">
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            ${escapeHtml((file.name || "Unknown").replace(/\.csv$/i, ""))}
          </span>
        `).join("")
      : `<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 9px;background:#F7FAFC;border:1.5px solid var(--border);border-radius:20px;font-size:11.5px;font-weight:500;color:var(--muted)">No export artifacts yet</span>`;
  }

  function renderDashboardCameraStatus(files = []) {
    const container = document.getElementById("dashboard-camera-status-list");
    if (!container) return;
    container.innerHTML = files.length
      ? files.map((file) => `
          <div class="camera-card" style="border-left:3px solid #48BB78">
            <div class="camera-name" style="display:flex;align-items:center;gap:6px">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#48BB78" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
              ${escapeHtml((file.name || "Unknown").replace(/\.csv$/i, ""))}
            </div>
            <div class="camera-stat"><span class="camera-stat-label">Rows</span><span class="camera-stat-val">${formatNumber(file.rows)}</span></div>
            <div class="camera-stat"><span class="camera-stat-label">Source</span><span class="camera-stat-val">${escapeHtml(file.path || file.name)}</span></div>
            <span class="camera-sync sync-ok">✓ Ready</span>
          </div>
        `).join("")
      : `<div class="camera-card" style="border-left:3px solid #CBD5E0"><div class="camera-name">No output files generated yet</div><div class="camera-stat"><span class="camera-stat-label">Images</span><span class="camera-stat-val">0</span></div><div class="camera-stat"><span class="camera-stat-label">Status</span><span class="camera-stat-val">Waiting for pipeline output</span></div></div>`;
  }

  function renderDashboardActivity(summary, validation, exportSummary) {
    const container = document.getElementById("dashboard-activity-list");
    if (!container) return;
    const items = [
      { badge: "Pipeline complete", badgeClass: "badge-blue", text: `${formatNumber(summary?.processed_images || 0)} images processed`, time: summary?.last_run?.date || "Unknown date" },
      { badge: "Review queue", badgeClass: "badge-yellow", text: `${formatNumber(summary?.pending_review || 0)} items need manual review`, time: "Current artifacts" },
      { badge: "Validation", badgeClass: "badge-yellow", text: `${formatNumber(validation?.outside_range || 0)} outside range, ${formatNumber(validation?.unprocessed || 0)} unprocessed`, time: "Current artifacts" },
      { badge: "Export files", badgeClass: "badge-green", text: exportSummary?.file_count ? `${formatNumber(exportSummary.file_count)} export file(s) ready` : "No export artifacts generated", time: exportSummary?.output_dir || "data/outputs/by_site" }
    ];

    container.innerHTML = items.map((item) => `
      <div class="activity-item">
        <span class="activity-badge ${item.badgeClass}">${escapeHtml(item.badge)}</span>
        <span class="activity-text">${escapeHtml(item.text)}</span>
        <span class="activity-time">${escapeHtml(item.time)}</span>
      </div>
    `).join("");
  }

  function applyDashboardSummary(summary, validation = app.state.validationData, exportSummary = app.state.exportData) {
    app.state.dashboardSummary = summary;
    const total = Number(summary?.total_images || 0);
    const processed = Number(summary?.processed_images || 0);
    const animals = Number(summary?.animals_detected || 0);
    const pendingReview = Number(summary?.pending_review || 0);
    const warnings = Number(summary?.warnings || 0);
    const runSuccess = Number(summary?.last_run?.success_rate || 0);
    const animalShare = getPercent(animals, processed || total);
    const otherShare = Math.max(100 - animalShare, 0);
    const exportFiles = exportSummary?.files || [];

    setDashboardStat("stat-total-images", total);
    setDashboardStat("stat-processed-images", processed);
    setDashboardStat("stat-animals-detected", animals);
    setDashboardStat("stat-pending-review", pendingReview);
    setDashboardStat("stat-warnings", warnings);
    setText("run-pct", formatPercent(runSuccess));
    document.getElementById("run-circle")?.setAttribute("stroke-dasharray", `${(Math.max(0, Math.min(100, runSuccess)) / 100) * 327} 327`);
    setText("run-success-count", formatNumber(processed));
    setText("run-success-rate", formatPercent(runSuccess));
    setText("run-failure-count", formatNumber(Math.max(total - processed, 0)));
    setText("species-total", formatNumber(animals));
    setText("species-total-label", animals ? "Animal rows" : "No animals");

    const legend = document.getElementById("species-legend-list");
    if (legend) {
      legend.innerHTML = `
        <div class="legend-item"><div class="legend-dot" style="background:#DD6B20"></div><span class="legend-name">Animal detections</span><span class="legend-count">${formatNumber(animals)}</span><span class="legend-pct" style="color:#DD6B20">${formatPercent(animalShare)}</span></div>
        <div class="legend-item"><div class="legend-dot" style="background:#CBD5E0"></div><span class="legend-name">Other / blank</span><span class="legend-count">${formatNumber(Math.max(processed - animals, 0))}</span><span class="legend-pct" style="color:#718096">${formatPercent(otherShare)}</span></div>
      `;
    }

    chartsApi.buildSpeciesDonut([{ value: animalShare, color: "#DD6B20" }, { value: otherShare, color: "#CBD5E0" }]);
    renderDashboardCameraChips(exportFiles);
    renderDashboardCameraStatus(exportFiles);
    renderDashboardActivity(summary, validation, exportSummary);
  }

  return {
    applyDashboardSummary
  };
}
