/** Validate actions for backend refresh, panel toggles, and preview updates. */
import { setText } from "../../utils/dom.js";
import { API_BASE, getAuthHeaders } from "../../services/core/http.js";

export function createValidateActions(app, api, renderApi) {

  async function loadValidationData({ showToastOnError = false } = {}) {
    try {
      const startDate = document.getElementById("dp-text-start")?.value || "";
      const endDate = document.getElementById("dp-text-end")?.value || "";
      const data = await api.getValidationIssues({ startDate, endDate });
      renderApi.applyValidationData(data);
      app.state.pageLoadState.validate = true;
      return data;
    } catch (error) {
      renderApi.applyValidationData(null);
      if (showToastOnError) app.showToast(error.message || "Unable to load validation issues", "warn");
      return null;
    }
  }

  async function runValidation() {
    const data = await loadValidationData({ showToastOnError: true });
    if (!data) return;
    if (app.state.dashboardSummary) {
      app.features.dashboard.applyDashboardSummary(app.state.dashboardSummary, data, app.state.exportData);
    }
    if (app.state.currentPage === "export") {
      app.features.export.applyExportData(app.state.exportData, data);
    }
    app.showToast("Validation refreshed from current output artifacts", "success");
  }

  async function previewTimeCorrection() {
    const offsetHours = Number(document.getElementById("offset-input")?.value || 0);
    const modal = document.getElementById("time-preview-modal");
    const body = document.getElementById("time-preview-modal-body");
    modal.style.display = "flex";
    body.innerHTML = "Loading...";
    try {
      const res = await fetch(`${API_BASE}/validate/preview-correction`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ offset_hours: offsetHours })
      });
      const data = await res.json();
      if (!data.rows?.length) {
        body.innerHTML = `<p style="color:var(--muted)">No images found.</p>`;
        return;
      }
      body.innerHTML = `
        <p style="font-size:13px;color:var(--muted);margin-bottom:12px">${data.total} image(s) will be updated</p>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr style="background:#F7FAFC">
            <th style="padding:8px;text-align:left;border-bottom:1px solid #E2E8F0">Camera</th>
            <th style="padding:8px;text-align:left;border-bottom:1px solid #E2E8F0">Image</th>
            <th style="padding:8px;text-align:left;border-bottom:1px solid #E2E8F0">Before</th>
            <th style="padding:8px;text-align:left;border-bottom:1px solid #E2E8F0">After</th>
          </tr></thead>
          <tbody>${data.rows.map(r => `<tr>
            <td style="padding:8px;border-bottom:1px solid #F0F0F0">${r.camera}</td>
            <td style="padding:8px;border-bottom:1px solid #F0F0F0">${r.image}</td>
            <td style="padding:8px;border-bottom:1px solid #F0F0F0;color:#718096">${r.before}</td>
            <td style="padding:8px;border-bottom:1px solid #F0F0F0;color:#2B6CB0;font-weight:600">${r.after}</td>
          </tr>`).join("")}</tbody>
        </table>
      `;
    } catch (e) {
      body.innerHTML = `<p style="color:red">Failed to load preview.</p>`;
    }
  }

  async function applyTimeCorrection() {
    const offsetHours = Number(document.getElementById("offset-input")?.value || 0);
    const selectImages = document.getElementById("time-correct-select")?.value || "All images";
    const startDate = document.getElementById("dp-text-start")?.value || "";
    const endDate = document.getElementById("dp-text-end")?.value || "";

    let selectKey = "all";
    if (selectImages.startsWith("All images outside range")) selectKey = "outside";
    else if (selectImages.startsWith("Images before deployment start")) selectKey = "before";
    else if (selectImages.startsWith("Images after deployment end")) selectKey = "after";

    try {
      app.showToast("Applying time correction…", "");
      const res = await fetch(`${API_BASE}/validate/apply-correction`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          offset_hours: offsetHours,
          select_images: selectKey,
          start_date: startDate,
          end_date: endDate
        })
      });
      const data = await res.json();
      app.showToast(data.message || "Time correction applied", "success");
      await loadValidationData({ showToastOnError: false });
    } catch (e) {
      app.showToast("Failed to apply time correction", "warn");
    }
  }

  function updateTimePreview(value) {
    const data = app.state.validationData;
    const sampleDate = data?.sample_date || "—";
    const sampleTime = data?.sample_time || "—";
    const [h, m, s] = (sampleTime !== "—" ? sampleTime : "00:00:00").split(":").map(Number);
    const corrected = ((h + Number(value || 0)) % 24 + 24) % 24;
    setText("time-preview-before", `Before: ${sampleDate} ${sampleTime}`);
    setText("time-preview-after", `After:  ${sampleDate} ${String(corrected).padStart(2, "0")}:${String(m || 0).padStart(2, "0")}:${String(s || 0).padStart(2, "0")}`);
  }

  return {
    loadValidationData,
    runValidation,
    previewTimeCorrection,
    applyTimeCorrection,
    toggleAffectedPanel: () => {
      const modal = document.getElementById("affected-modal");
      if (modal) modal.style.display = modal.style.display === "flex" ? "none" : "flex";
    },
    toggleUnprocPanel: () => document.getElementById("unproc-panel")?.classList.toggle("open"),
    updateTimePreview
  };
}