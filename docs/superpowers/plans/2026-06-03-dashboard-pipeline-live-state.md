# Dashboard Pipeline Live State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dashboard pipeline cards reflect live upload, classify, review, and export state, and reset cleanly for each new batch or rerun.

**Architecture:** Rework the dashboard pipeline state builder so it no longer assumes a fixed "latest completed run" snapshot. Instead, it will merge live backend pipeline status with local upload/review/export signals already present in the UI. The dashboard renderer will consume that unified snapshot and update the four visible cards: Upload, Classify, Review, and Export.

**Tech Stack:** Vanilla JavaScript modules in `ui/src`, localStorage-backed feature state, Node test runner tests in `tests/*.mjs`.

---

### Task 1: Update the pipeline state tests first

**Files:**
- Modify: `tests/dashboardPipeline.test.mjs`
- Create: `tests/dashboardPipelineExport.test.mjs`

- [ ] **Step 1: Write the failing test**

```javascript
test("dashboard pipeline shows upload, classify, review, and export states from live inputs", () => {
  const state = buildDashboardPipelineState({
    pipelineStatus: {
      status: "running",
      current_step: "Run SpeciesNet",
      progress: { step: "Run SpeciesNet", percent: 44, details: { processed_images: 44, total_images: 100 } }
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

  assert.deepEqual(state.steps.map((step) => step.key), ["upload", "classify", "review", "export"]);
  assert.equal(state.steps[0].state, "active");
  assert.equal(state.steps[0].percentLabel, "72%");
  assert.equal(state.steps[1].state, "active");
  assert.equal(state.steps[1].percentLabel, "44%");
  assert.equal(state.steps[2].state, "done");
  assert.equal(state.steps[2].percentLabel, "24%");
  assert.equal(state.steps[3].state, "idle");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/dashboardPipeline.test.mjs`
Expected: FAIL because the current pipeline builder still renders five steps and does not accept live upload/review/export snapshots.

- [ ] **Step 3: Write minimal implementation**

```javascript
export function buildDashboardPipelineState({ pipelineStatus, uploadSnapshot, reviewSnapshot, exportSnapshot } = {}) {
  // Merge live signals into four dashboard steps.
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tests/dashboardPipeline.test.mjs tests/dashboardPipelineExport.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboardPipeline.test.mjs tests/dashboardPipelineExport.test.mjs
git commit -m "test: cover live dashboard pipeline cards"
```

### Task 2: Implement the live dashboard pipeline snapshot and export tracking

**Files:**
- Modify: `ui/src/features/dashboard/dashboardPipeline.mjs`
- Modify: `ui/src/features/dashboard/dashboardRender.js`
- Modify: `ui/src/features/dashboard/partials/overview.html`
- Modify: `ui/src/features/export/exportActions.js`
- Modify: `ui/src/features/pipeline/pipelineActions.js`
- Modify: `ui/src/features/pipeline/pipelineState.js`
- Modify: `ui/src/features/drive/manualUploadFlow.js`
- Modify: `ui/src/features/drive/driveMain.js`

- [ ] **Step 1: Write the failing test**

```javascript
test("export is complete only after final_results.csv is downloaded for the current run", () => {
  // Use localStorage to mark a downloaded export from an older run.
  // Build the dashboard snapshot for a newer batch and expect export to be pending.
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/dashboardPipelineExport.test.mjs`
Expected: FAIL because no export download completion marker is tracked yet.

- [ ] **Step 3: Write minimal implementation**

```javascript
// Add a small localStorage-backed export completion marker keyed to the active run/batch.
// Expose a manual upload snapshot getter and update the dashboard renderer to pass all live inputs.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tests/dashboardPipeline.test.mjs tests/dashboardPipelineExport.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/features/dashboard/dashboardPipeline.mjs ui/src/features/dashboard/dashboardRender.js ui/src/features/dashboard/partials/overview.html ui/src/features/dashboard/dashboard.css ui/src/features/dashboard/dashboardActivity.mjs ui/src/features/export/exportActions.js ui/src/features/pipeline/pipelineActions.js ui/src/features/pipeline/pipelineState.js ui/src/features/drive/manualUploadFlow.js ui/src/features/drive/driveMain.js tests/dashboardPipeline.test.mjs tests/dashboardPipelineExport.test.mjs
git commit -m "feat: make dashboard pipeline cards live"
```

### Task 3: Verify the broader dashboard and pipeline suite

**Files:**
- Modify: none
- Test: `tests/dashboardLayout.test.mjs`, `tests/dashboardActivity.test.mjs`, `tests/pipelineState.test.mjs`, `tests/pipelineRender.test.mjs`

- [ ] **Step 1: Run the dashboard and pipeline tests**

Run: `node --test tests/dashboardLayout.test.mjs tests/dashboardActivity.test.mjs tests/pipelineState.test.mjs tests/pipelineRender.test.mjs`
Expected: PASS with the dashboard now showing four pipeline steps and the live state helper staying compatible with the existing pipeline/status pages.

- [ ] **Step 2: Fix any mismatches inline**

If a test fails, update the state resolver or rendering logic rather than loosening the assertions.

- [ ] **Step 3: Commit**

```bash
git add ui/src/features/dashboard ui/src/features/export ui/src/features/pipeline ui/src/features/drive tests
git commit -m "test: verify dashboard pipeline live state"
```
