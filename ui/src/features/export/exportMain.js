/** Export feature entry that composes artifact rendering and export action flows. */
import { createExportActions } from "./exportActions.js";
import { createExportApi } from "./exportApi.js";
import { createExportRender } from "./exportRender.js";

export function createExportFeature(app) {
  const api = createExportApi();
  const renderApi = createExportRender(app);
  const actionApi = createExportActions(app, api, renderApi);

  return {
    ...renderApi,
    ...actionApi
  };
}
