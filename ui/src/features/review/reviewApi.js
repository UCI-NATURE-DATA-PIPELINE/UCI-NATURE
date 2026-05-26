/** Review feature wrappers around backend queue retrieval. */
import { getReviewItems, saveReviewDecision, applyReviewDecisions } from "../../services/api.js";
export function createReviewApi() {
  return {
    getReviewItems,
    saveReviewDecision,
    applyReviewDecisions
  };
}
