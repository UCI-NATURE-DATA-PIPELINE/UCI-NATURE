/** Auth feature entry that composes login state, rendering, and user actions. */
import { createAuthActions } from "./authActions.js";
import { createAuthApi } from "./authApi.js";
import { createAuthRender } from "./authRender.js";
import { createAuthState } from "./authState.js";

export function createAuthFeature(app) {
  const api = createAuthApi();
  const stateApi = createAuthState(app);
  const renderApi = createAuthRender(stateApi);
  const actionApi = createAuthActions(app, api, stateApi, renderApi);

  return {
    ...stateApi,
    ...renderApi,
    ...actionApi
  };
}
