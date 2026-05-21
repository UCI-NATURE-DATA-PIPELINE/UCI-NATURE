/** Validate actions for backend refresh, panel toggles, and preview updates. */
import { setText } from "../../utils/dom.js";
import { API_BASE, getAuthHeaders } from "../../services/core/http.js";

export function createValidateActions(app, api, renderApi) {

  async function loadValidationData({ showToastOnError = false } = {}) {
    try {
      const data = await api.getValidationIssues();
      renderApi.applyValidationData(data);
      app.state.pageLoadState.validate = true;
      return data;
    } catch (error) {
      renderApi.applyValidationData(null);
      if (showToastOnError) app.showToast(error.message || "Unable to load validation issues", "warn");
      return null;
    }
  }

  async function onPageEnter() {
    // Data loads only when user clicks Run Validation, not on page entry
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
      app.showToast("Validation complete", "success");  }

  function getTotalOffsetHours() {
    const years = Number(document.getElementById("offset-years")?.value || 0);
    const months = Number(document.getElementById("offset-months")?.value || 0);
    const days = Number(document.getElementById("offset-days")?.value || 0);
    const hours = Number(document.getElementById("offset-input")?.value || 0);
    return (years * 8760) + (months * 730) + (days * 24) + hours;
  }

  function resolveSampleDateTime() {
    const data = app.state.validationData;
    const sampleDate =
      data?.sample_date ||
      (data?.files || []).map(f => f.sample_date || "").filter(Boolean).sort()[0] ||
      "";
    const sampleTime =
      data?.sample_time ||
      (data?.files || []).map(f => f.sample_time || "").filter(Boolean)[0] ||
      "00:00:00";
    return { sampleDate, sampleTime };
  }

  function updateTimePreviewMulti() {
    const { sampleDate, sampleTime } = resolveSampleDateTime();
    if (!sampleDate) {
      setText("time-preview-before", "Before: — —");
      setText("time-preview-after", "After:  — —");
      return;
    }
    const totalHours = getTotalOffsetHours();
    const [h, m, s] = sampleTime.split(":").map(Number);
    const correctedH = ((h + (totalHours % 24)) % 24 + 24) % 24;
    const totalDays = Math.floor(totalHours / 24);
    const baseDate = new Date(sampleDate + "T" + sampleTime);
    baseDate.setDate(baseDate.getDate() + totalDays);
    baseDate.setHours(correctedH);
    const correctedDate = baseDate.toISOString().split("T")[0];
    setText("time-preview-before", `Before: ${sampleDate} ${sampleTime}`);
    setText("time-preview-after", `After:  ${correctedDate} ${String(correctedH).padStart(2,"0")}:${String(m||0).padStart(2,"0")}:${String(s||0).padStart(2,"0")}`);
  }

  function updateTimePreview(value) {
    updateTimePreviewMulti();
  }

  async function previewTimeCorrection() {
    const totalHours = getTotalOffsetHours();
    if (totalHours === 0) {
      app.showToast("Set a time offset before previewing", "warn");
      return;
    }
    const modal = document.getElementById("time-preview-modal");
    const body = document.getElementById("time-preview-modal-body");
    modal.style.display = "flex";
    body.innerHTML = `<p style="color:var(--muted);font-size:13px">Loading preview…</p>`;
    try {
      const res = await fetch(`${API_BASE}/validate/preview-correction`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ offset_hours: totalHours })
      });
      const data = await res.json();

      if (!data.rows?.length) {
        body.innerHTML = `<p style="color:var(--muted);font-size:13px">No images found.</p>`;
        return;
      }

      // Group rows by folder
      const grouped = {};
      for (const row of data.rows) {
        const folder = row.folder || "Unknown Folder";
        if (!grouped[folder]) grouped[folder] = [];
        grouped[folder].push(row);
      }

      const folderCount = Object.keys(grouped).length;
      let html = `<p style="font-size:13px;color:var(--muted);margin-bottom:16px">
        ${data.total} image(s) across ${folderCount} folder(s) will be updated
      </p>`;

      for (const [folder, rows] of Object.entries(grouped)) {
        html += `
          <div style="margin-bottom:20px">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#718096" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
              <span style="font-size:13px;font-weight:700;color:#2D3748">${folder}</span>
              <span style="font-size:12px;color:var(--muted)">${rows.length} image(s)</span>
            </div>
            <table style="width:100%;border-collapse:collapse;font-size:12.5px">
              <thead>
                <tr style="background:#F7FAFC">
                  <th style="padding:7px 10px;text-align:left;border-bottom:1px solid #E2E8F0;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em">Camera</th>
                  <th style="padding:7px 10px;text-align:left;border-bottom:1px solid #E2E8F0;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em">Image</th>
                  <th style="padding:7px 10px;text-align:left;border-bottom:1px solid #E2E8F0;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em">Before</th>
                  <th style="padding:7px 10px;text-align:left;border-bottom:1px solid #E2E8F0;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em">After</th>
                </tr>
              </thead>
              <tbody>
                ${rows.map(r => `<tr>
                  <td style="padding:7px 10px;border-bottom:1px solid #F0F0F0;color:#4A5568;font-family:'JetBrains Mono',monospace">${r.camera || "—"}</td>
                  <td style="padding:7px 10px;border-bottom:1px solid #F0F0F0;color:#4A5568;font-family:'JetBrains Mono',monospace">${r.image || "—"}</td>
                  <td style="padding:7px 10px;border-bottom:1px solid #F0F0F0;color:#718096;font-family:'JetBrains Mono',monospace">${r.before}</td>
                  <td style="padding:7px 10px;border-bottom:1px solid #F0F0F0;color:#276749;font-weight:600;font-family:'JetBrains Mono',monospace">${r.after}</td>
                </tr>`).join("")}
              </tbody>
            </table>
          </div>`;
      }

      body.innerHTML = html;
    } catch (e) {
      body.innerHTML = `<p style="color:red;font-size:13px">Failed to load preview.</p>`;
    }
  }

  async function applyTimeCorrection() {
    const totalHours = getTotalOffsetHours();
    try {
      app.showToast("Applying time correction…", "");
      const res = await fetch(`${API_BASE}/validate/apply-correction`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          offset_hours: totalHours,
          select_images: "all"
        })
      });
      const data = await res.json();
      app.showToast("Time correction applied successfully", "success");      document.getElementById("offset-years").value = 0;
      document.getElementById("offset-months").value = 0;
      document.getElementById("offset-days").value = 0;
      document.getElementById("offset-input").value = 0;
      updateTimePreviewMulti();
      await loadValidationData({ showToastOnError: false });
    } catch (e) {
      app.showToast("Failed to apply time correction", "warn");
    }
  }

  return {
    loadValidationData,
    onPageEnter,
    runValidation,
    previewTimeCorrection,
    applyTimeCorrection,
    updateTimePreview,
    updateTimePreviewMulti,
    toggleAffectedPanel: () => {
      const modal = document.getElementById("affected-modal");
      if (modal) modal.style.display = modal.style.display === "flex" ? "none" : "flex";
    },
    toggleUnprocPanel: () => document.getElementById("unproc-panel")?.classList.toggle("open"),
  };
}