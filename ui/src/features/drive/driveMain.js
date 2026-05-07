/** Drive feature entry that composes state, render, events, api, and sync modules. */
import { createDriveApi } from "./driveApi.js";
import { createDriveEvents } from "./driveEvents.js";
import { createDriveRender } from "./driveRender.js";
import { createDriveSelection } from "./driveSelection.js";
import { createDriveSettings } from "./driveSettings.js";
import { createDriveState } from "./driveState.js";
import { createDriveSync } from "./driveSync.js";
import { createDriveUtils } from "./driveUtils.js";
import { createManualUploadFlow } from "./manualUploadFlow.js";

export function createDriveFeature(app) {
  const api = createDriveApi();
  const stateApi = createDriveState();
  const utilsApi = createDriveUtils(stateApi);
  const renderApi = createDriveRender(app, stateApi, utilsApi);
  const selectionApi = createDriveSelection(app, api, stateApi, renderApi);
  const syncApi = createDriveSync(app, api, stateApi, renderApi);
  const settingsApi = createDriveSettings(app, api, stateApi, renderApi, selectionApi);
  const eventApi = createDriveEvents(app, renderApi);
  const manualUploadFlow = createManualUploadFlow(app);

  return {
    ...stateApi,
    ...renderApi,
    ...selectionApi,
    ...settingsApi,
    ...syncApi,
    ...eventApi,
    ...utilsApi,
    initializeManualUpload: manualUploadFlow.initialize,
    refreshManualUpload: manualUploadFlow.refresh,
    loadDriveStatusSummary: api.getDriveStatus
  };
}
