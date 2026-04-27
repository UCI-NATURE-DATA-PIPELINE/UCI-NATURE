/** App bootstrap helper for constructing all feature modules used by the shell. */
import { createAuthFeature } from "../features/auth/authMain.js";
import { createDashboardFeature } from "../features/dashboard/dashboardMain.js";
import { createDriveFeature } from "../features/drive/driveMain.js";
import { createExportFeature } from "../features/export/exportMain.js";
import { createPipelineFeature } from "../features/pipeline/pipelineMain.js";
import { createReviewFeature } from "../features/review/reviewMain.js";
import { createStatisticsFeature } from "../features/statistics/statisticsMain.js";
import { createValidateFeature } from "../features/validate/validateMain.js";

export function registerFeatures(app) {
  app.features.auth = createAuthFeature(app);
  app.features.drive = createDriveFeature(app);
  app.features.pipeline = createPipelineFeature(app);
  app.features.dashboard = createDashboardFeature(app);
  app.features.review = createReviewFeature(app);
  app.features.validate = createValidateFeature(app);
  app.features.export = createExportFeature(app);
  app.features.statistics = createStatisticsFeature(app);
}
