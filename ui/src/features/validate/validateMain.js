/** Validate feature entry that composes summaries, tables, and validation actions. */
import { createValidateActions } from "./validateActions.js";
import { createValidateApi } from "./validateApi.js";
import { createValidateRender } from "./validateRender.js";
import { createValidateTables } from "./validateTables.js";

export function createValidateFeature(app) {
  const api = createValidateApi();
  const tableApi = createValidateTables(app);
  const renderApi = createValidateRender(app, tableApi);
  const actionApi = createValidateActions(app, api, renderApi);

  return {
    ...tableApi,
    ...renderApi,
    ...actionApi
  };
}
