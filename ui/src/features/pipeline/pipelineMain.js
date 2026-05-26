/** Pipeline feature entry that composes run status, polling, and submission actions. */
import { createPipelineActions } from "./pipelineActions.js";
import { createPipelineApi } from "./pipelineApi.js";
import { createPipelinePolling } from "./pipelinePolling.js";
import { createPipelineRender } from "./pipelineRender.js";
import { createPipelineState } from "./pipelineState.js";

export function createPipelineFeature(app) {
  const api = createPipelineApi();
  const stateApi = createPipelineState(app);
  const renderApi = createPipelineRender(app, stateApi);
  let pollingApi = null;

  async function loadPipelineResults({ silent = false } = {}) {
    try {
      const results = await api.getPipelineResults();
      renderApi.applyPipelineResults(results);
      return results;
    } catch (error) {
      if (!silent) app.showToast(error.message || "Unable to load pipeline results", "warn");
      renderApi.applyPipelineResults(null);
      return null;
    }
  }

  async function loadPipelineStatus({ silent = false } = {}) {
    try {
      const status = await api.getPipelineStatus();
      renderApi.applyPipelineStatus(status);
      if (status?.status === "running") {
        renderApi.applyPipelineResults(null);
        pollingApi.startPipelineStatusPolling();
      } else {
        pollingApi.stopPipelineStatusPolling();
        await loadPipelineResults({ silent: true });
      }
      return status;
    } catch (error) {
      if (!silent) app.showToast(error.message || "Unable to load pipeline status", "warn");
      renderApi.applyPipelineStatus(null);
      renderApi.applyPipelineResults(null);
      pollingApi.stopPipelineStatusPolling();
      app.applyBackendHealthStatus?.(null);
      return null;
    }
  }

  pollingApi = createPipelinePolling(app, () => loadPipelineStatus({ silent: true }));
  const actionApi = createPipelineActions(app, api, renderApi, loadPipelineStatus, loadPipelineResults);

  return {
    ...stateApi,
    ...renderApi,
    ...pollingApi,
    ...actionApi,
    loadPipelineResults,
    loadPipelineStatus
  };
}
