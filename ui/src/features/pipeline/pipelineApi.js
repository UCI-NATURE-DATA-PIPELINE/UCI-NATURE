/** Pipeline feature wrappers around backend run and status service calls. */
import {
  downloadPipelineResultFile,
  getPipelineResults,
  getPipelineStatus,
  runPipeline
} from "../../services/api.js";

export function createPipelineApi() {
  return {
    downloadPipelineResultFile,
    getPipelineResults,
    getPipelineStatus,
    runPipeline
  };
}
