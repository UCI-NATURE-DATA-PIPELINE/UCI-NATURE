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

    setText("range-warn-title", `${formatNumber(data?.outside_range || 0)} images outside deployment range`);
    setHTML("range-warn-body", Number(data?.outside_range || 0) > 0
      ? "Current output files include rows flagged as <strong>outside deployment interval</strong>."
      : "No generated output rows are outside the deployment range.");
    setText("val-sub-datetime", Number(data?.outside_range || 0) > 0
      ? "Some rows are flagged outside the deployment interval"
      : "No rows are outside the deployment interval");
    setText("val-badge-datetime", `${formatNumber(data?.outside_range || 0)} outside range`);
    setText("val-run-note", data ? "Last validated: Current pipeline artifacts" : "Validation data unavailable");
    document.getElementById("range-warn-box")?.style.setProperty("display", Number(data?.outside_range || 0) > 0 ? "flex" : "none");

    // Unprocessed badge and panel title
    const unprocessed = Number(data?.unprocessed || 0);
    setText("val-badge-unprocessed", `${formatNumber(unprocessed)} unprocessed`);
    setText("unproc-panel-title", `${formatNumber(unprocessed)} images — ML processing incomplete`);

    // Time correction select options with real counts
    const outsideRange = Number(data?.outside_range || 0);
    const beforeStart = Number(data?.before_start || 0);
    const afterEnd = Number(data?.after_end || 0);
    const optOutside = document.getElementById("opt-outside-range");
    const optBefore = document.getElementById("opt-before-start");
    const optAfter = document.getElementById("opt-after-end");
    if (optOutside) optOutside.textContent = `All images outside range (${formatNumber(outsideRange)})`;
    if (optBefore) optBefore.textContent = `Images before deployment start (${formatNumber(beforeStart)})`;
    if (optAfter) optAfter.textContent = `Images after deployment end (${formatNumber(afterEnd)})`;

    // Time preview with real sample date/time
    const sampleDate = data?.sample_date || "—";
    const sampleTime = data?.sample_time || "—";
    setText("time-preview-before", `Before: ${sampleDate} ${sampleTime}`);
    setText("time-preview-after", `After:  ${sampleDate} ${sampleTime}`);

    // Warn labels with current deployment dates
    const startLabel = document.getElementById("dp-text-start")?.value || "—";
    const endLabel = document.getElementById("dp-text-end")?.value || "—";
    setText("warn-start-label", startLabel);
    setText("warn-end-label", endLabel);

    tableApi.renderAffectedImages(data);
    tableApi.renderUnprocessedImages(data);
  }

  return {
    applyValidationData
  };
}