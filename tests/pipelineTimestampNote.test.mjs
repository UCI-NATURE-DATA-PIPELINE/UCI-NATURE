import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const PIPELINE_HTML = readFileSync("ui/src/features/pipeline/pipeline.html", "utf8");
const PIPELINE_CSS = readFileSync("ui/src/features/pipeline/pipeline.css", "utf8");

test("timestamp note renders as a pinned upload-style callout", () => {
  assert.match(PIPELINE_HTML, /id="run-timestamp-note" hidden/);
  assert.match(PIPELINE_HTML, /id="drive-timestamp-note" hidden/);
  assert.match(PIPELINE_HTML, /class="upload-note-card run-timestamp-note"/);
  assert.match(PIPELINE_HTML, /class="upload-note-card run-timestamp-note"/);
  assert.match(PIPELINE_HTML, /\n\s+Note\n\s+<\/div>/);
  assert.match(PIPELINE_HTML, /If Stop still reports another run in progress, wait a few minutes and try again\./);
  assert.match(PIPELINE_CSS, /\.run-timestamp-note \{\s*position:absolute;/);
  assert.match(PIPELINE_CSS, /\.upload-note-card \{\s*background:#FFFBEB;/);
});
