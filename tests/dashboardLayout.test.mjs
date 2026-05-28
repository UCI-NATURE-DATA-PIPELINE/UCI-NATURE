import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const OVERVIEW = readFileSync("ui/src/features/dashboard/partials/overview.html", "utf8");
const INSIGHTS = readFileSync("ui/src/features/dashboard/partials/insights.html", "utf8");

test("dashboard includes a species histogram panel", () => {
  assert.match(OVERVIEW, /dashboard-overview-panel--species/);
  assert.match(OVERVIEW, /dashboard-species-chart/);
  assert.match(OVERVIEW, /dashboard-park-toggle/);
});

test("dashboard insight cards use compact grid wrappers", () => {
  assert.match(INSIGHTS, /dashboard-insights-grid/);
  assert.match(INSIGHTS, /dashboard-insight-card/);
  assert.match(INSIGHTS, /dashboard-insight-card--summary/);
  assert.match(INSIGHTS, /dashboard-insight-card--activity/);
  assert.doesNotMatch(INSIGHTS, /Camera Sites/);
  assert.doesNotMatch(INSIGHTS, /Recent Activity/);
});
