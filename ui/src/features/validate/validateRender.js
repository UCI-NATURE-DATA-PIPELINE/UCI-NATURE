/** Validate rendering for summary cards and warning callouts. */
import { setHTML, setText } from "../../utils/dom.js";
import { formatNumber } from "../../utils/format.js";

export function createValidateRender(app, tableApi) {
  function applyValidationData(data) {
    app.state.validationData = data;
    const totalRecords = Number((data?.files || []).reduce((sum, item) => sum + Number(item.rows || 0), 0));
    const warnings = Number(data?.outside_range || 0) + Number(data?.column_issue_count || 0);
    const errors = Number(data?.unprocessed || 0);
    const valid = Math.max(totalRecords - warnings, 0);

    setText("val-total", formatNumber(totalRecords));
    setText("val-valid", formatNumber(valid));
    setText("val-warnings", formatNumber(warnings));
    setText("val-errors", formatNumber(errors));

    // Columns badge
    const colsTotal = Number(data?.columns_total || 0);
    const colsPresent = Number(data?.columns_present ?? colsTotal);
    const hasFiles = (data?.files || []).length > 0;
    if (hasFiles && colsTotal > 0) {
      setText("val-badge-columns", `${colsPresent} / ${colsTotal} columns`);
    } else {
      setText("val-badge-columns", `-- / -- columns`);
    }

    setText("val-run-note", data ? "Last validated: Current pipeline artifacts" : "Validation data unavailable");

    // Unprocessed badge and panel title
    const unprocessed = Number(data?.unprocessed || 0);
    setText("val-badge-unprocessed", `${formatNumber(unprocessed)} unprocessed`);
    setText("unproc-panel-title", `${formatNumber(unprocessed)} images — ML processing incomplete`);

    // Resolve sample_date — use top-level field first, then fall back to
    // the earliest sample_date found across the files array.
    const fileSampleDate = (data?.files || [])
      .map(f => f.sample_date || "")
      .filter(Boolean)
      .sort()[0] || "";
    const fileSampleTime = (data?.files || [])
      .map(f => f.sample_time || "")
      .filter(Boolean)[0] || "";

    const sampleDate = data?.sample_date || fileSampleDate || "";
    const sampleTime = data?.sample_time || fileSampleTime || "";

    // Current image date info box
    const infoBox = document.getElementById("current-date-info");
    if (infoBox) {
      if (sampleDate) {
        infoBox.style.display = "block";
        setText("current-date-value", sampleDate);
        setText("current-time-value", sampleTime || "—");
        const folderName = (data?.files || []).find(f => f.file?.includes("_results"))?.file?.replace("_results.csv", "") || "Current dataset";
        setText("current-date-folder", folderName);
      } else {
        infoBox.style.display = "none";
      }
    }

    // Time preview — set before value, then trigger multi-field preview update
    setText("time-preview-before", sampleDate ? `Before: ${sampleDate} ${sampleTime}` : "Before: — —");
    setText("time-preview-after", sampleDate ? `After:  ${sampleDate} ${sampleTime}` : "After:  — —");
    if (typeof window.updateTimePreviewMulti === "function") window.updateTimePreviewMulti();

    tableApi.renderAffectedImages(data);
    tableApi.renderUnprocessedImages(data);
  }

  return {
    applyValidationData
  };
}