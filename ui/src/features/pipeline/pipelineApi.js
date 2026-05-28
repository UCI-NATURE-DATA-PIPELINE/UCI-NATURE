/** Pipeline feature wrappers around backend run and status service calls. */
import {
  cancelPipeline,
  downloadPipelineResultFile,
  getPipelineResults,
  getPipelineStatus,
  runPipeline
} from "../../services/api.js";

export function createPipelineApi() {
  return {
    downloadPipelineResultFile,
    cancelPipeline,
    getPipelineResults,
    getPipelineStatus,
    runPipeline
  };
}
