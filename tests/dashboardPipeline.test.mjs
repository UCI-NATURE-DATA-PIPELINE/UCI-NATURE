import test from "node:test";
import assert from "node:assert/strict";
import { buildDashboardPipelineState } from "../ui/src/features/dashboard/dashboardPipeline.mjs";

test("idle dashboard pipeline state is neutral", () => {
  const state = buildDashboardPipelineState(null);

  assert.deepEqual(
    state.steps.map((step) => step.state),
    ["idle", "idle", "idle", "idle"]
  );
  assert.deepEqual(
    state.steps.map((step) => step.percentLabel),
    ["—", "—", "—", "—"]
  );
  assert.equal(state.steps[0].countLabel, "—");
});

test("running dashboard pipeline state uses live progress", () => {
  const state = buildDashboardPipelineState({
    pipelineStatus: {
      status: "running",
      current_step: "Run SpeciesNet",
      progress: {
        step: "Run SpeciesNet",
        percent: 44,
        details: {
          processed_images: 44,
          total_images: 100
        }
      }
    }
  });

  assert.deepEqual(
    state.steps.map((step) => step.state),
    ["done", "active", "idle", "idle"]
  );
  assert.deepEqual(
    state.steps.map((step) => step.percentLabel),
    ["100%", "44%", "—", "—"]
  );
  assert.equal(state.steps[0].countLabel, "100 images");
  assert.equal(state.steps[1].countLabel, "44 / 100 images");
});

test("dashboard pipeline shows live upload and review progress", () => {
  const state = buildDashboardPipelineState({
    pipelineStatus: {
      status: "running",
      current_step: "Run SpeciesNet",
      progress: {
        step: "Run SpeciesNet",
        percent: 44,
        details: {
          processed_images: 44,
          total_images: 100
        }
      }
    },
    uploadSnapshot: {
      status: "uploading",
      percent: 72,
      done: 72,
      total: 100
    },
    reviewSnapshot: {
      total: 50,
      reviewed: 12,
      percent: 24
    },
    exportSnapshot: {
      ready: true,
      downloaded: false
    }
  });

  assert.deepEqual(
    state.steps.map((step) => step.key),
    ["upload", "classify", "review", "export"]
  );
  assert.equal(state.steps[0].state, "active");
  assert.equal(state.steps[0].percentLabel, "72%");
  assert.equal(state.steps[1].state, "active");
  assert.equal(state.steps[1].percentLabel, "44%");
  assert.equal(state.steps[2].state, "active");
  assert.equal(state.steps[2].percentLabel, "24%");
  assert.equal(state.steps[2].countLabel, "12 / 50 items");
  assert.equal(state.steps[3].state, "idle");
  assert.equal(state.steps[3].percentLabel, "Pending");
});
