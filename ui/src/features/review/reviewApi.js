/** Review feature wrappers around backend queue retrieval. */
import { getReviewItems, saveReviewDecision } from "../../services/api.js";
export function createReviewApi() {
  return {
    getReviewItems,
    saveReviewDecision
  };
}
