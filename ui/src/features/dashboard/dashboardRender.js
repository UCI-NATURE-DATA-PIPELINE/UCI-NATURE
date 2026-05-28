/** Dashboard rendering for summary cards, export chips, and activity lists. */
import { setText } from "../../utils/dom.js";
import { escapeHtml, formatNumber, formatPercent, getPercent } from "../../utils/format.js";
import { buildDashboardActivityItems } from "./dashboardActivity.mjs";
import { buildDashboardPipelineState } from "./dashboardPipeline.mjs";

const PIPELINE_STEP_IDS = {
  upload: {
    root: "dashboard-pipeline-step-upload",
    pct: "dashboard-pipeline-percent-upload",
    fill: "dashboard-pipeline-fill-upload",
    count: "dashboard-pipeline-count-upload",
    dot: "dashboard-pipeline-dot-upload"
  },
  classify: {
    root: "dashboard-pipeline-step-classify",
    pct: "dashboard-pipeline-percent-classify",
    fill: "dashboard-pipeline-fill-classify",
    count: "dashboard-pipeline-count-classify",
    dot: "dashboard-pipeline-dot-classify"
  },
  review: {
    root: "dashboard-pipeline-step-review",
    pct: "dashboard-pipeline-percent-review",
    fill: "dashboard-pipeline-fill-review",
    count: "dashboard-pipeline-count-review",
    dot: "dashboard-pipeline-dot-review"
  },
  validate: {
    root: "dashboard-pipeline-step-validate",
    pct: "dashboard-pipeline-percent-validate",
    fill: "dashboard-pipeline-fill-validate",
    count: "dashboard-pipeline-count-validate",
    dot: "dashboard-pipeline-dot-validate"
  },
  export: {
    root: "dashboard-pipeline-step-export",
    pct: "dashboard-pipeline-percent-export",
    fill: "dashboard-pipeline-fill-export",
    count: "dashboard-pipeline-count-export",
    dot: "dashboard-pipeline-dot-export"
  }
};

function renderPipelineDot(state) {
  if (state === "done") {
    return `
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <polyline points="20 6 9 17 4 12"></polyline>
      </svg>
    `;
  }

  if (state === "active") {
    return `
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="4" fill="#fff"></circle>
      </svg>
    `;
  }

  return "";
}

function updatePipelineStep(step) {
  const ids = PIPELINE_STEP_IDS[step.key];
  if (!ids) return;

  const root = document.getElementById(ids.root);
  const pct = document.getElementById(ids.pct);
  const fill = document.getElementById(ids.fill);
  const count = document.getElementById(ids.count);
  const dot = document.getElementById(ids.dot);

  if (root) {
    root.classList.remove("done", "active", "idle");
    root.classList.add(step.state);
  }
  if (pct) pct.textContent = step.percentLabel;
  if (fill) fill.style.width = step.state === "done" ? "100%" : step.state === "active" ? `${step.percentLabel}` : "0%";
  if (count) count.textContent = step.countLabel;
  if (dot) dot.innerHTML = renderPipelineDot(step.state);
}

function renderDashboardPipelineState(status) {
  const model = buildDashboardPipelineState(status);

  const flowFill = document.getElementById("pipeline-flow-fill");
  if (flowFill) {
    flowFill.style.width = `${model.flowPercent}%`;
    flowFill.style.setProperty("--fill-pct", `${model.flowPercent}%`);
  }

  model.steps.forEach(updatePipelineStep);
}

export function createDashboardRender(app, chartsApi) {
  let speciesToggleBound = false;

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

  function renderDashboardExportChips(files = []) {
    const container = document.getElementById("dashboard-export-chip-list");
    if (!container) return;
    container.innerHTML = files.length
      ? files.map((file) => `
          <span style="display:inline-flex;align-items:center;gap:5px;padding:3px 9px;background:#F0FFF4;border:1.5px solid #9AE6B4;border-radius:20px;font-size:11.5px;font-weight:600;color:#276749">
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            ${escapeHtml((file.label || file.name || "Unknown").replace(/\.csv$/i, ""))}
          </span>
        `).join("")
      : `<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 9px;background:#F7FAFC;border:1.5px solid var(--border);border-radius:20px;font-size:11.5px;font-weight:500;color:var(--muted)">No export artifacts yet</span>`;
  }

  function renderDashboardSpeciesHistogram(app, chartsApi, speciesHistogram) {
    const toggleContainer = document.getElementById("dashboard-park-toggle");
    const canvas = document.getElementById("dashboard-species-chart");
    const emptyState = document.getElementById("dashboard-species-empty");
    if (!toggleContainer || !canvas || !emptyState) return;

    const parks = Array.isArray(speciesHistogram?.parks) ? speciesHistogram.parks : [];
    if (!parks.length) {
      toggleContainer.innerHTML = "";
      canvas.hidden = true;
      emptyState.hidden = false;
      chartsApi.buildSpeciesHistogram(app, canvas, null);
      return;
    }

    const selectedKey = parks.some((park) => park.key === app.state.dashboardSpeciesHistogramSelected)
      ? app.state.dashboardSpeciesHistogramSelected
      : speciesHistogram?.default_park_key || parks[0].key;
    const selectedPark = parks.find((park) => park.key === selectedKey) || parks[0];
    app.state.dashboardSpeciesHistogramSelected = selectedPark.key;
    app.state.dashboardSpeciesHistogram = speciesHistogram;

    toggleContainer.innerHTML = parks.map((park) => `
      <button type="button" class="dashboard-park-toggle-btn${park.key === selectedPark.key ? " active" : ""}" data-park-key="${escapeHtml(park.key)}">
        ${escapeHtml(park.label)}
      </button>
    `).join("");

    canvas.hidden = !selectedPark.total_detections || !selectedPark.species_labels.length;
    emptyState.hidden = selectedPark.total_detections > 0 && selectedPark.species_labels.length > 0;

    if (canvas.hidden) {
      chartsApi.buildSpeciesHistogram(app, canvas, null);
      return;
    }

    chartsApi.buildSpeciesHistogram(app, canvas, {
      label: selectedPark.label,
      labels: selectedPark.species_labels,
      values: selectedPark.species_values
    });
  }

  function renderDashboardActivity(summary, validation, exportSummary, pipelineStatus) {
    const container = document.getElementById("dashboard-activity-list");
    if (!container) return;
    const items = buildDashboardActivityItems({
      summary,
      validation,
      exportSummary,
      pipelineStatus
    });

    container.innerHTML = items.map((item) => `
      <div class="activity-item">
        <span class="activity-badge ${item.badgeClass}">${escapeHtml(item.badge)}</span>
        <span class="activity-text">${escapeHtml(item.text)}</span>
        <span class="activity-time">${escapeHtml(item.time)}</span>
      </div>
    `).join("");
  }

  function applyDashboardSummary(summary, validation = app.state.validationData, exportSummary = app.state.exportData, pipelineStatus = app.state.pipelineStatus, speciesHistogram = app.state.dashboardSpeciesHistogram) {
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
    setText(
      "stat-total-images-sub",
      summary?.last_run?.batch
        ? `Latest batch ${summary.last_run.batch}`
        : summary?.last_run?.date
          ? `Updated ${summary.last_run.date}`
          : "Manifest total"
    );
    setText("stat-processed-images-sub", total ? `${formatPercent(getPercent(processed, total))} complete` : "Awaiting run data");
    setText("stat-animals-detected-sub", summary ? `${formatNumber(animals)} detections` : "Resolved outputs");
    setText("stat-pending-review-sub", `${formatNumber(pendingReview)} open in queue`);
    setText("stat-warnings-sub", validation ? `${formatNumber(warnings)} validation issue${warnings === 1 ? "" : "s"}` : "Latest validation");
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
    renderDashboardExportChips(exportFiles);
    renderDashboardActivity(summary, validation, exportSummary, pipelineStatus);
    renderDashboardSpeciesHistogram(app, chartsApi, speciesHistogram);

    if (!speciesToggleBound) {
      const toggleContainer = document.getElementById("dashboard-park-toggle");
      if (toggleContainer) {
        toggleContainer.addEventListener("click", (event) => {
          const button = event.target.closest(".dashboard-park-toggle-btn");
          if (!button) return;
          const parkKey = button.dataset.parkKey;
          if (!parkKey || parkKey === app.state.dashboardSpeciesHistogramSelected) return;
          app.state.dashboardSpeciesHistogramSelected = parkKey;
          renderDashboardSpeciesHistogram(app, chartsApi, app.state.dashboardSpeciesHistogram);
        });
        speciesToggleBound = true;
      }
    }

    renderDashboardPipelineState(pipelineStatus);
  }

  function applyDashboardPipelineState(pipelineStatus = app.state.pipelineStatus) {
    renderDashboardPipelineState(pipelineStatus);
  }

  return {
    applyDashboardSummary,
    applyDashboardPipelineState
  };
}
