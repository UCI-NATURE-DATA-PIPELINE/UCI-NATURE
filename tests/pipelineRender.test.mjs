import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const RENDER = readFileSync("ui/src/features/pipeline/pipelineRender.js", "utf8");

test("run model progress card hides after the pipeline reaches a terminal state", () => {
  assert.match(RENDER, /panel\.style\.display = state === "running" \? "block" : "none";/);
  assert.match(RENDER, /const panelVisible = state === "running";/);
  assert.match(RENDER, /const noteCard = document\.getElementById\(surface\.noteCardId\);/);
  assert.match(RENDER, /noteCard\.hidden = state === "running";/);
  assert.doesNotMatch(RENDER, /panel\.style\.display = \(!status \|\| state === "idle"\) \? "none" : "block";/);
});
