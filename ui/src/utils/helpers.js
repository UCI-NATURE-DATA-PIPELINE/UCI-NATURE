/** Shared non-DOM helpers for Drive, pipeline, and review feature modules. */
import { createEmptyDriveSyncState, DRIVE_FOLDER_SOURCE_LABELS } from "../state/appState.js";
import { formatNumber, getSpeciesEmoji } from "./format.js";

export function normalizeDriveSyncStatus(value) {
  const next = {
    ...createEmptyDriveSyncState(),
    ...(value || {})
  };

  next.folder = next.folder || null;
  next.selected_folder = next.selected_folder || null;
  next.status = String(next.status || "idle").toLowerCase();
  next.available_count = Number(next.available_count || 0);
  next.discovered_count = Number(next.discovered_count || 0);
  if (!next.available_count && next.discovered_count) {
    next.available_count = next.discovered_count;
  }
  next.downloaded_count = Number(next.downloaded_count || 0);
  next.discovery_complete = Boolean(next.discovery_complete || next.status === "completed");
  next.cancellation_requested = Boolean(next.cancellation_requested);
  next.requested_total = Math.max(0, Number(next.requested_total || 0));
  // Remaining: prefer the requested target during discovery, the real
  // discovered total after listing completes.
  next.remaining_count = Number(
    next.remaining_count != null
      ? next.remaining_count
      : next.requested_total > 0
        ? Math.max(
            (next.discovery_complete && next.discovered_count > 0
              ? Math.min(next.requested_total, next.discovered_count)
              : next.requested_total) -
              Math.min(
                next.downloaded_count,
                next.discovery_complete && next.discovered_count > 0
                  ? Math.min(next.requested_total, next.discovered_count)
                  : next.requested_total
              ),
            0
          )
        : next.discovery_complete
        ? Math.max(next.discovered_count - next.downloaded_count, 0)
        : Math.max(next.discovered_count - next.downloaded_count, 0)
  );
  // Progress percent rules:
  //   discovery done                → downloaded / discovered
  //   discovery in progress + limit → downloaded / requested_total
  //   discovery in progress + no limit → 0 (indeterminate UI)
  let computedPercent = 0;
  if (next.requested_total > 0) {
    const progressTarget = next.discovery_complete && next.discovered_count > 0
      ? Math.min(next.requested_total, next.discovered_count)
      : next.requested_total;
    computedPercent = progressTarget > 0
      ? Math.round((Math.min(next.downloaded_count, progressTarget) / progressTarget) * 100)
      : 0;
  } else if (next.status === "completed") {
    computedPercent = 100;
  } else if (next.discovery_complete && next.discovered_count > 0) {
    computedPercent = Math.round((next.downloaded_count / next.discovered_count) * 100);
  }
  next.progress_percent = Number(
    next.progress_percent != null ? next.progress_percent : computedPercent
  );
  next.progress_percent = Math.max(0, Math.min(100, next.progress_percent));
  next.selected_folder_matches = Boolean(
    next.selected_folder_matches != null
      ? next.selected_folder_matches
      : next.folder?.id && next.selected_folder?.id && next.folder.id === next.selected_folder.id
  );
  next.source_ready = Boolean(next.source_ready && next.selected_folder_matches);
  return next;
}

export function normalizeDriveSyncLimitValue(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null;
}

export function formatDriveSyncLimitLabel(value) {
  const normalized = normalizeDriveSyncLimitValue(value);
  return normalized ? `${formatNumber(normalized)} files` : "All files";
}

export function normalizeDriveFolderOptions(folders) {
  if (!Array.isArray(folders)) {
    return [];
  }

  const seen = new Set();
  const normalized = [];

  folders.forEach((folder) => {
    const id = String(folder?.id || "").trim();
    const name = String(folder?.name || "").trim();
    if (!id || !name || seen.has(id)) {
      return;
    }

    const source = String(folder?.source || "").trim().toLowerCase();
    normalized.push({
      ...folder,
      id,
      name,
      source: source || "my_drive"
    });
    seen.add(id);
  });

  normalized.sort((left, right) => {
    const byName = left.name.localeCompare(right.name, undefined, { sensitivity: "base" });
    if (byName !== 0) {
      return byName;
    }

    const leftSource = DRIVE_FOLDER_SOURCE_LABELS[left.source] || left.source || "";
    const rightSource = DRIVE_FOLDER_SOURCE_LABELS[right.source] || right.source || "";
    const bySource = leftSource.localeCompare(rightSource, undefined, { sensitivity: "base" });
    if (bySource !== 0) {
      return bySource;
    }

    return left.id.localeCompare(right.id);
  });

  return normalized;
}

export function formatDriveFolderOptionLabel(folder) {
  const label = String(folder?.name || "").trim();
  const sourceKey = String(folder?.source || "").trim().toLowerCase();
  const sourceLabel = DRIVE_FOLDER_SOURCE_LABELS[sourceKey] || "";

  return sourceLabel && sourceKey !== "my_drive"
    ? `${label} (${sourceLabel})`
    : label;
}

export function getPipelineMetrics(status) {
  const result = status?.result || {};
  const steps = result?.steps || {};
  const manifestRows = Number(steps?.manifest?.rows_written || 0);
  const processedRows = Number(
    steps?.metadata_merged?.rows_written
      || steps?.metadata_exif?.rows_written
      || 0
  );
  const reviewItems = Number(steps?.postprocess?.review_items || 0);
  const exportedRows = Number(steps?.output?.rows_written || 0);
  const failureCount = status?.status === "completed"
    ? Math.max(manifestRows - processedRows, 0)
    : null;
  const throughput = result?.elapsed_seconds && processedRows
    ? processedRows / Number(result.elapsed_seconds)
    : null;

  return {
    manifestRows,
    processedRows,
    remainingRows: status?.status === "completed" ? Math.max(manifestRows - processedRows, 0) : null,
    reviewItems,
    exportedRows,
    failureCount,
    throughput
  };
}

export function getPipelineSourceMode(status, uploadTab) {
  return String(
    status?.result?.source?.mode ||
    status?.payload?.source_mode ||
    (uploadTab === "drive" ? "drive" : "local")
  ).toLowerCase();
}

export function getPipelineOverallStatusLabel(status) {
  const state = String(status?.status || "idle").toLowerCase();
  const currentStep = String(status?.progress?.step || status?.current_step || "").toLowerCase();

  if (!status?.run_id) return "Idle";
  if (state === "running" && currentStep === "queued") return "Queued";
  if (state === "running") return "Running";
  if (state === "completed") return "Completed";
  if (state === "failed") return "Failed";
  if (state === "cancelled" || state === "stopped") return "Stopped";
  return "Idle";
}

export function getPipelineCurrentStepLabel(status) {
  return status?.progress?.step || status?.current_step || (status?.run_id ? "Waiting for backend updates" : "Waiting for a run");
}

export function normalizeReviewItem(item) {
  const species = (item?.species || "unknown").trim() || "unknown";
  const speciesLower = species.toLowerCase();
  // Trust the backend `animal_detected` flag when present (the backend
  // already simplifies labels and demotes uncertain blanks). Fall back to
  // a token check for older payloads.
  const animalDetected = item?.animal_detected != null
    ? Boolean(item.animal_detected)
    : !["blank", "human", "vehicle", "no cv result", "unknown", ""].includes(speciesLower);

  return {
    id: item?.id,
    filename: item?.filename || `review-item-${item?.id || "unknown"}`,
    filepath: item?.filepath,
    file_path: item?.file_path,
    species,
    confidence: Number(item?.confidence || 0),
    animalDetected,
    humanDetected: speciesLower === "human",
    camera: item?.camera || "Unknown",
    datetime: item?.datetime || "Unknown",
    burst: item?.reason ? `Reason: ${item.reason}` : "Manual review item",
    status: item?.status || "pending",
    emoji: getSpeciesEmoji(speciesLower),
    reason: item?.reason || "",
    // Backend-supplied priority bucket (animals first, blanks last).
    priority: typeof item?.priority === "number" ? item.priority : 99
  };
}

export function getFilteredReviewItems(items, filters) {
  let nextItems = [...items];

  if (filters.reviewFilter !== "all") {
    nextItems = nextItems.filter((item) => item.status === filters.reviewFilter);
  }

  if (filters.humanFilterOnly) {
    nextItems = nextItems.filter((item) => item.humanDetected);
  }

  if (filters.sortMode === "low-confidence") {
    // Explicit user override — sort by ascending confidence regardless of
    // the default animal-first ordering.
    nextItems.sort((left, right) => left.confidence - right.confidence);
  } else {
    // Default: keep the backend's animal-first priority ordering. Within
    // a bucket, higher confidence wins.
    nextItems.sort((left, right) => {
      if (left.priority !== right.priority) return left.priority - right.priority;
      return right.confidence - left.confidence;
    });
  }

  return nextItems;
}
