import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const RENDER = readFileSync("ui/src/features/pipeline/pipelineRender.js", "utf8");

test("run model progress card hides after the pipeline reaches a terminal state", () => {
  assert.match(RENDER, /const isVisible = isRunning \|\| isCompleted \|\| isFailed;/);
  assert.match(RENDER, /panel\.style\.display = isVisible \? "block" : "none";/);
  assert.match(RENDER, /const panelVisible = state === "running" \|\| state === "completed" \|\| state === "failed";/);
  assert.match(RENDER, /panel\.classList\.remove\("state-running", "state-completed", "state-failed"\);/);
  assert.match(RENDER, /progressLabel\.textContent = isRunning \? status\?\.progress\?\.step \|\| "Processing images…" : isCompleted \? "Processing Complete" : isFailed \? "Pipeline Failed" : "No active pipeline run";/);
  assert.match(RENDER, /const terminalProcessedCount = Number\.isFinite\(Number\(metrics\.processedRows\)\) \? Number\(metrics\.processedRows\) : null;/);
  assert.match(RENDER, /const terminalTotalCount = Number\.isFinite\(Number\(metrics\.manifestRows\)\) \? Number\(metrics\.manifestRows\) : null;/);
  assert.match(RENDER, /processedValue\.textContent = processedCount === null \? "—" : formatNumber\(processedCount\);/);
  assert.match(RENDER, /remainingValue\.textContent = remainingCount === null \? "—" : formatNumber\(remainingCount\);/);
  assert.match(RENDER, /fill\.classList\.remove\("state-completed", "state-failed"\);/);
});
