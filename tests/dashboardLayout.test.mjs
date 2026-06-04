import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const OVERVIEW = readFileSync("ui/src/features/dashboard/partials/overview.html", "utf8");
const INSIGHTS = readFileSync("ui/src/features/dashboard/partials/insights.html", "utf8");
const DASHBOARD_MAIN = readFileSync("ui/src/features/dashboard/dashboardMain.js", "utf8");
const DASHBOARD_RENDER = readFileSync("ui/src/features/dashboard/dashboardRender.js", "utf8");

test("dashboard does not expose the species histogram panel while it is on hold", () => {
  assert.doesNotMatch(OVERVIEW, /dashboard-overview-panel--species/);
  assert.doesNotMatch(OVERVIEW, /dashboard-species-chart/);
  assert.doesNotMatch(OVERVIEW, /dashboard-park-toggle/);
  assert.doesNotMatch(OVERVIEW, /Validate/);
});

test("dashboard insight cards use compact grid wrappers", () => {
  assert.match(INSIGHTS, /dashboard-insights-grid/);
  assert.match(INSIGHTS, /dashboard-insight-card/);
  assert.match(INSIGHTS, /dashboard-insight-card--summary/);
  assert.match(INSIGHTS, /dashboard-insight-card--activity/);
  assert.doesNotMatch(INSIGHTS, /Camera Sites/);
  assert.doesNotMatch(INSIGHTS, /Recent Activity/);
});

test("dashboard no longer fetches or renders the histogram while it is on hold", () => {
  assert.doesNotMatch(DASHBOARD_MAIN, /getDashboardSpeciesHistogram/);
  assert.doesNotMatch(DASHBOARD_RENDER, /dashboard-park-toggle/);
  assert.doesNotMatch(DASHBOARD_RENDER, /dashboard-species-chart/);
});
