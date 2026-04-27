/** Dashboard feature wrappers around summary and export artifact API calls. */
import { getDashboardSummary, startExport as startExportRequest } from "../../services/api.js";

export function createDashboardApi() {
  return {
    getDashboardSummary,
    startExportRequest
  };
}
