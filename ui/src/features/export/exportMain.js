/** Export feature entry that composes artifact rendering and export action flows. */
import { createExportActions } from "./exportActions.js";
import { createExportApi } from "./exportApi.js";
import { createExportRender } from "./exportRender.js";

export function createExportFeature(app) {
  const api       = createExportApi();
  const renderApi = createExportRender(app);
  const actionApi = createExportActions(app, api, renderApi);

  // Event delegation: handle all .export-download-btn clicks
  // Safe to attach once at the document level — won't double-fire
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".export-download-btn");
    if (!btn) return;
    const filename = btn.dataset.filename;
    if (filename) actionApi.downloadFile(filename);
  });

  return {
    ...renderApi,
    ...actionApi
  };
}
