/** Review feature entry that composes queue rendering, actions, and review controls. */
import { createReviewActions } from "./reviewActions.js";
import { createReviewApi } from "./reviewApi.js";
import { createReviewControls } from "./reviewControls.js";
import { createReviewRender } from "./reviewRender.js";
import { createReviewState } from "./reviewState.js";

export function createReviewFeature(app) {
  const api = createReviewApi();
  const stateApi = createReviewState(app);
  const renderApi = createReviewRender(app, stateApi);
  const actionApi = createReviewActions(app, api, stateApi, renderApi);
  const controlApi = createReviewControls(app, stateApi, renderApi, actionApi);

  return {
    ...renderApi,
    ...actionApi,
    ...controlApi
  };
}
