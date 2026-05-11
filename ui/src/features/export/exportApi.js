/** Export feature wrappers around validation and artifact-loading backend calls. */
import { getValidationIssues, startExport as startExportRequest } from "../../services/api.js";
import { downloadExportFile } from "../../services/exportApi.js";

export function createExportApi() {
  return {
    getValidationIssues,
    startExportRequest,
    downloadExportFile
  };
}
