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

test("latest completed pipeline run is ignored after a newer upload or export mutation", () => {
  const originalLocalStorage = global.localStorage;
  const mutationTimestamp = String(Date.parse("2026-05-28T10:06:00Z"));
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
    ]),
    uci_nature_pipeline_dashboard_mutation: mutationTimestamp
  });

  try {
    const stateApi = createPipelineState({
      state: {
        uploadTab: "main",
        driveSyncState: {}
      }
    });
    const snapshot = stateApi.getLatestCompletedRunStatus();

    assert.equal(snapshot, null);
  } finally {
    global.localStorage = originalLocalStorage;
  }
});

test("a newer completed pipeline run replaces the stale dashboard snapshot", () => {
  const originalLocalStorage = global.localStorage;
  const mutationTimestamp = String(Date.parse("2026-05-28T10:06:00Z"));
  global.localStorage = createLocalStorageMock({
    uci_nature_run_history: JSON.stringify([
      {
        run_id: "run-2",
        status: "completed",
        started_at: "2026-05-29T09:00:00Z",
        finished_at: "2026-05-29T09:10:00Z",
        current_step: "Export results",
        progress_percent: 100,
        progress_details: {
          total_images: 180,
          processed_images: 180
        },
        elapsed_seconds: 600,
        batch_size: "all",
        manifest_rows: 180,
        processed_rows: 180,
        review_items: 12,
        exported_rows: 168,
        failure_count: 0,
        throughput: 3,
        notes: ["re-run"]
      }
    ]),
    uci_nature_pipeline_dashboard_mutation: mutationTimestamp
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
    assert.equal(snapshot.run_id, "run-2");
    assert.equal(snapshot.progress.details.total_images, 180);
  } finally {
    global.localStorage = originalLocalStorage;
  }
});
