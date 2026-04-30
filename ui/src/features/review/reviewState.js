/** Review feature state helpers for the currently visible review queue items. */
import { getFilteredReviewItems } from "../../utils/helpers.js";

export function createReviewState(app) {
  function currentItems() {
    return getFilteredReviewItems(app.state.reviewItems, {
      reviewFilter: app.state.reviewFilter,
      humanFilterOnly: app.state.humanFilterOnly,
      sortMode: app.state.sortMode
    });
  }

  return {
    currentItems
  };
}
