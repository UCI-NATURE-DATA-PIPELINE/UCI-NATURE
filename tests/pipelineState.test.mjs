import test from "node:test";
import assert from "node:assert/strict";
import { createPipelineState } from "../ui/src/features/pipeline/pipelineState.js";

function createLocalStorageMock(initialValues = {}) {
  const store = new Map(Object.entries(initialValues));
  return {
    getItem(key) {
      return store.has(key) ? store.get(key) : null;
    },
    setItem(key, value) {
      store.set(key, String(value));
    },
    removeItem(key) {
      store.delete(key);
    }
  };
}

test("latest completed pipeline run is rehydrated for the dashboard", () => {
  const originalLocalStorage = global.localStorage;
  global.localStorage = createLocalStorageMock({
    uci_nature_run_history: JSON.stringify([
      {
        run_id: "run-1",
        status: "completed",
        started_at: "2026-05-28T10:00:00Z",
        finished_at: "2026-05-28T10:05:00Z",
        current_step: "Export results",
        progress_percent: 100,
        progress_details: {
          total_images: 120,
          processed_images: 120
        },
        elapsed_seconds: 300,
        batch_size: "all",
        manifest_rows: 120,
        processed_rows: 120,
        review_items: 8,
        exported_rows: 112,
        failure_count: 0,
        throughput: 2.4,
        notes: ["finished"]
      }
    ])
  });

  try {
    const stateApi = createPipelineState({
      state: {
        uploadTab: "main",
        driveSyncState: {}
      }
    });
    const snapshot = stateApi.getLatestCompletedRunStatus();

    assert.ok(snapshot);
    assert.equal(snapshot.status, "completed");
    assert.equal(snapshot.progress.step, "Export results");
    assert.equal(snapshot.progress.percent, 100);
    assert.equal(snapshot.progress.details.total_images, 120);
    assert.equal(snapshot.progress.details.processed_images, 120);
    assert.equal(snapshot.result.source.image_count, 120);
  } finally {
    global.localStorage = originalLocalStorage;
  }
});
