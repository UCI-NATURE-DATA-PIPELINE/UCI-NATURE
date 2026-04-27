/** Validate table rendering for affected-range and unprocessed-image lists. */
import { escapeHtml, formatNumber } from "../../utils/format.js";

export function createValidateTables(app) {
  function renderAffectedImages(data = app.state.validationData) {
    const body = document.getElementById("affected-table-body");
    if (!body) return;
    const files = (data?.files || []).filter((item) => Number(item.outside_range || 0) > 0);
    body.innerHTML = files.length
      ? files.map((item) => `<tr><td>${escapeHtml(item.file)}</td><td>${escapeHtml((item.file || "Unknown").replace(/\.csv$/i, ""))}</td><td>Not available in current validation output</td><td>${formatNumber(item.outside_range)} row(s) flagged outside deployment interval</td></tr>`).join("")
      : `<tr><td colspan="4" style="color:var(--muted)">No out-of-range rows were reported by the current validation artifacts.</td></tr>`;
  }

  function renderUnprocessedImages(data = app.state.validationData) {
    const body = document.getElementById("unproc-table-body");
    if (!body) return;
    const unprocessed = Number(data?.unprocessed || 0);
    body.innerHTML = unprocessed
      ? `<tr><td>manifest.csv</td><td>All locations</td><td>Not available in current validation output</td><td>${formatNumber(unprocessed)} image(s) are missing rows in ml_outputs.csv</td></tr>`
      : `<tr><td colspan="4" style="color:var(--muted)">All manifest rows have corresponding ML output rows.</td></tr>`;
  }

  return {
    renderAffectedImages,
    renderUnprocessedImages
  };
}
