/** Export rendering for artifact summaries, rows, and filename previews. */
import { setHTML, setText } from "../../utils/dom.js";
import { escapeHtml, formatNumber } from "../../utils/format.js";

export function createExportRender(app) {
  function buildExportFolderRows(files = []) {
    return files.length
      ? files.map((file) => `<div class="export-folder-row"><div class="export-folder-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#2B6CB0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg></div><div style="flex:1;min-width:0"><div class="export-folder-name">${escapeHtml((file.name || "Unknown").replace(/\.csv$/i, ""))}</div><div class="export-folder-sub">${formatNumber(file.rows)} rows · ${escapeHtml(file.path || file.name)}</div></div><div class="export-folder-actions"><span class="export-sync-badge synced"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>Ready</span><button class="export-folder-view-btn" onclick="showToast(this.dataset.path,'')" data-path="${escapeHtml(file.path || file.name)}">View Artifact</button></div></div>`).join("")
      : `<div class="export-folder-row"><div class="export-folder-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#718096" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg></div><div style="flex:1;min-width:0"><div class="export-folder-name">No export files available</div><div class="export-folder-sub">Run the pipeline to generate data/outputs/by_site files.</div></div></div>`;
  }

  function syncExportFilenamePreview() {
    const input = document.getElementById("export-filename");
    const preview = document.getElementById("export-filename-preview");
    if (input && preview) preview.textContent = `${input.value}.${app.state.selectedFormat}`;
  }

  function applyExportData(data, validation = app.state.validationData) {
    app.state.exportData = data;
    setText("export-val-total", formatNumber(data?.total_rows || 0));
    setText("export-val-human", "75");
    setText("export-val-burst", formatNumber(data?.file_count || 0));
    setHTML("export-folder-list", buildExportFolderRows(data?.files || []));
    setText("export-status-title", validation ? `${formatNumber(Number(validation?.outside_range || 0) + Number(validation?.unprocessed || 0) + Number(validation?.column_issue_count || 0))} validation issues found` : "Validation checks are clear");
    setText("export-status-sub", validation ? `${formatNumber(validation?.unprocessed || 0)} unprocessed images and ${formatNumber(validation?.outside_range || 0)} out-of-range timestamps — these records will be excluded from the export automatically` : "Current export artifacts are ready with no validation exclusions.");
    setHTML("export-main-btn", `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>Export ${formatNumber(data?.total_rows || 0)} Records to Google Drive`);
    syncExportFilenamePreview();
  }

  return {
    applyExportData,
    syncExportFilenamePreview
  };
}
