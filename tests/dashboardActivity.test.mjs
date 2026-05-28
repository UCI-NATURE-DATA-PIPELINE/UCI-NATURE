import test from "node:test";
import assert from "node:assert/strict";
import { buildDashboardActivityItems } from "../ui/src/features/dashboard/dashboardActivity.mjs";

test("dashboard activity feed uses live backend summaries", () => {
  const items = buildDashboardActivityItems({
    summary: {
      pending_review: 12,
      last_run: {
        date: "May 24, 2026",
        duration: "5 min 12 s",
        batch: "#4"
      }
    },
    validation: {
      outside_range: 3,
      unprocessed: 2,
      column_issue_count: 1
    },
    exportSummary: {
      file_count: 4,
      total_rows: 1280
    },
    pipelineStatus: {
      run_id: "run-42",
      status: "running",
      started_at: "2026-05-24T11:30:00.000Z",
      progress: {
        step: "Run SpeciesNet",
        percent: 44
      }
    }
  });

  assert.equal(items.length, 4);
  assert.equal(items[0].badge, "Pipeline");
  assert.match(items[0].text, /44% complete/);
  assert.match(items[1].text, /12 items waiting in review/);
  assert.match(items[2].text, /6 validation issues detected/);
  assert.match(items[3].text, /4 export files ready/);
});
