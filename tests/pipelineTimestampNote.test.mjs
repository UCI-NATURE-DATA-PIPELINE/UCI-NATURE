import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const PIPELINE_HTML = readFileSync("ui/src/features/pipeline/pipeline.html", "utf8");
const PIPELINE_CSS = readFileSync("ui/src/features/pipeline/pipeline.css", "utf8");

test("run model note renders as an inline tooltip icon", () => {
  assert.match(PIPELINE_HTML, /<span class="has-tooltip run-row-tooltip">/);
  assert.match(PIPELINE_HTML, /<span class="help-icon help-icon-yellow">!<\/span>/);
  assert.match(PIPELINE_HTML, /If Stop still reports another run in progress, wait a few minutes and try again\./);
  assert.match(PIPELINE_HTML, /<span style="font-size:12\.5px;color:var\(--muted\)" id="run-ready-note">-- images ready to process<\/span>/);
  assert.match(PIPELINE_HTML, /<span style="font-size:12\.5px;color:var\(--muted\)" id="drive-run-note"><\/span>/);
  assert.doesNotMatch(PIPELINE_HTML, /run-timestamp-note|drive-timestamp-note|upload-note-card/);
  assert.match(PIPELINE_CSS, /\.run-row-tooltip \{\s*display:inline-flex;/);
  assert.match(PIPELINE_CSS, /\.run-row-tooltip \.help-icon \{\s*margin-left:0;/);
});
