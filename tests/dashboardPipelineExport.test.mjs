import test from "node:test";
import assert from "node:assert/strict";
import { buildDashboardPipelineState } from "../ui/src/features/dashboard/dashboardPipeline.mjs";

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

test("export card becomes complete only for the downloaded final results of the current run", () => {
  const originalLocalStorage = global.localStorage;
  global.localStorage = createLocalStorageMock({
    uci_nature_pipeline_export_download: JSON.stringify({
      run_id: "run-7",
      file_name: "final_results.csv",
      downloaded_at: "2026-06-03T10:10:00.000Z"
    })
  });

  try {
    const state = buildDashboardPipelineState({
      pipelineStatus: {
        status: "completed",
        run_id: "run-7",
        current_step: "Export results",
        finished_at: "2026-06-03T10:05:00.000Z",
        progress: {
          step: "Export results",
          percent: 100,
          details: {
            total_images: 120,
            processed_images: 120
          }
        },
        result: {
          source: {
            image_count: 120
          }
        }
      },
      exportSnapshot: {
        ready: true,
        downloaded: true,
        files: [{ name: "final_results.csv" }]
      }
    });

    assert.equal(state.steps[3].state, "done");
    assert.equal(state.steps[3].percentLabel, "100%");
  } finally {
    global.localStorage = originalLocalStorage;
  }
});

test("export card resets to pending after a newer batch mutation", () => {
  const originalLocalStorage = global.localStorage;
  global.localStorage = createLocalStorageMock({
    uci_nature_pipeline_export_download: JSON.stringify({
      run_id: "run-7",
      file_name: "final_results.csv",
      downloaded_at: "2026-06-03T10:10:00.000Z"
    }),
    uci_nature_pipeline_dashboard_mutation: String(Date.parse("2026-06-03T10:20:00.000Z"))
  });

  try {
    const state = buildDashboardPipelineState({
      pipelineStatus: {
        status: "completed",
        run_id: "run-7",
        current_step: "Export results",
        finished_at: "2026-06-03T10:05:00.000Z",
        progress: {
          step: "Export results",
          percent: 100,
          details: {
            total_images: 120,
            processed_images: 120
          }
        },
        result: {
          source: {
            image_count: 120
          }
        }
      },
      exportSnapshot: {
        ready: true,
        downloaded: true,
        files: [{ name: "final_results.csv" }]
      }
    });

    assert.equal(state.steps[3].state, "idle");
    assert.equal(state.steps[3].percentLabel, "Pending");
  } finally {
    global.localStorage = originalLocalStorage;
  }
});
