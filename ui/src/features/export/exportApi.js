/** Export feature wrappers around validation and artifact-loading backend calls. */
import { getValidationIssues, startExport as startExportRequest } from "../../services/api.js";

export function createExportApi() {
  return {
    getValidationIssues,
    startExportRequest
  };
}
