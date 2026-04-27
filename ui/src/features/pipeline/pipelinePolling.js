/** Pipeline polling helpers for backend status refresh while runs are active. */
import { getPipelineSourceMode } from "../../utils/helpers.js";

export function createPipelinePolling(app, loadStatus) {
  let pipelineStatusPollId = null;

  function startPipelineStatusPolling() {
    if (pipelineStatusPollId) return;
    pipelineStatusPollId = window.setInterval(() => {
      void loadStatus();
      if (app.state.runningModel && getPipelineSourceMode(app.state.pipelineStatus, app.state.uploadTab) === "drive") {
        void app.features.drive.loadDriveSyncStatus({ silent: true });
      }
    }, 2000);
  }

  function stopPipelineStatusPolling() {
    if (!pipelineStatusPollId) return;
    window.clearInterval(pipelineStatusPollId);
    pipelineStatusPollId = null;
  }

  return {
    startPipelineStatusPolling,
    stopPipelineStatusPolling
  };
}
