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
    setText("range-warn-title", `${formatNumber(data?.outside_range || 0)} images outside deployment range`);
    setHTML("range-warn-body", Number(data?.outside_range || 0) > 0 ? "Current output files include rows flagged as <strong>outside deployment interval</strong>." : "No generated output rows are outside the deployment range.");
    setText("val-sub-datetime", Number(data?.outside_range || 0) > 0 ? "Some rows are flagged outside the deployment interval" : "No rows are outside the deployment interval");
    setText("val-badge-datetime", `${formatNumber(data?.outside_range || 0)} outside range`);
    setText("val-run-note", data ? "Last validated: Current pipeline artifacts" : "Validation data unavailable");
    document.getElementById("range-warn-box")?.style.setProperty("display", Number(data?.outside_range || 0) > 0 ? "flex" : "none");

    tableApi.renderAffectedImages(data);
    tableApi.renderUnprocessedImages(data);
  }

  return {
    applyValidationData
  };
}
