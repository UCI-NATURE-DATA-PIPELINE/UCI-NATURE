/** Validate feature wrappers around backend validation artifact requests. */
import { getValidationIssues } from "../../services/api.js";

export function createValidateApi() {
  return {
    getValidationIssues: (opts) => getValidationIssues(opts)
  };
}