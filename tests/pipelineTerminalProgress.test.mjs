import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const PIPELINE_CSS = readFileSync("ui/src/features/pipeline/pipeline.css", "utf8");

test("terminal pipeline progress states use green and red bars", () => {
  assert.match(PIPELINE_CSS, /\.run-progress-panel\.state-completed \.run-prog-fill \{/);
  assert.match(PIPELINE_CSS, /\.run-progress-panel\.state-failed \.run-prog-fill \{/);
  assert.match(PIPELINE_CSS, /\.run-progress-panel\.state-completed \.run-prog-fill::after \{ content:none; \}/);
  assert.match(PIPELINE_CSS, /\.run-progress-panel\.state-completed \.proc-dot \{/);
});
