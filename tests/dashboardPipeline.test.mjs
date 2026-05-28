import test from "node:test";
import assert from "node:assert/strict";
import { buildDashboardPipelineState } from "../ui/src/features/dashboard/dashboardPipeline.mjs";

test("idle dashboard pipeline state is neutral", () => {
  const state = buildDashboardPipelineState(null);

  assert.deepEqual(
    state.steps.map((step) => step.state),
    ["idle", "idle", "idle", "idle", "idle"]
  );
  assert.deepEqual(
    state.steps.map((step) => step.percentLabel),
    ["—", "—", "—", "—", "—"]
  );
  assert.equal(state.steps[0].countLabel, "—");
});

test("running dashboard pipeline state uses live progress", () => {
  const state = buildDashboardPipelineState({
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
  });

  assert.deepEqual(
    state.steps.map((step) => step.state),
    ["done", "active", "idle", "idle", "idle"]
  );
  assert.deepEqual(
    state.steps.map((step) => step.percentLabel),
    ["100%", "44%", "—", "—", "—"]
  );
  assert.equal(state.steps[0].countLabel, "100 images");
  assert.equal(state.steps[1].countLabel, "44 / 100 images");
});
