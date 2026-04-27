/** Statistics feature wrappers around backend analytics summary calls. */
import { getStatisticsSummary } from "../../services/api.js";

export function createStatisticsApi() {
  return {
    getStatisticsSummary
  };
}
