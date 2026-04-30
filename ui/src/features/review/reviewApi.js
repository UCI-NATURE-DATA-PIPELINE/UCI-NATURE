/** Review feature wrappers around backend queue retrieval. */
import { getReviewItems } from "../../services/api.js";

export function createReviewApi() {
  return {
    getReviewItems
  };
}
