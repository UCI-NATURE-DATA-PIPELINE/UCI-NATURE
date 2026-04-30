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
  next.discovered_count = Number(next.discovered_count || 0);
  next.downloaded_count = Number(next.downloaded_count || 0);
  next.remaining_count = Number(
    next.remaining_count != null
      ? next.remaining_count
      : Math.max(next.discovered_count - next.downloaded_count, 0)
  );
  next.progress_percent = Number(
    next.progress_percent != null
      ? next.progress_percent
      : next.discovered_count
        ? Math.round((next.downloaded_count / next.discovered_count) * 100)
        : next.status === "completed"
          ? 100
          : 0
  );
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
  return normalized ? `First ${formatNumber(normalized)} files` : "All files";
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
  return "Idle";
}

export function getPipelineCurrentStepLabel(status) {
  return status?.progress?.step || status?.current_step || (status?.run_id ? "Waiting for backend updates" : "Waiting for a run");
}

export function normalizeReviewItem(item) {
  const species = (item?.species || "Unknown").trim() || "Unknown";
  const speciesLower = species.toLowerCase();

  return {
    id: item?.id,
    filename: item?.filename || `review-item-${item?.id || "unknown"}`,
    species,
    confidence: Number(item?.confidence || 0),
    animalDetected: !["blank", "human", "vehicle", "no cv result"].includes(speciesLower),
    humanDetected: speciesLower.includes("human"),
    camera: item?.camera || "Unknown",
    datetime: item?.datetime || "Unknown",
    burst: item?.reason ? `Reason: ${item.reason}` : "Manual review item",
    status: item?.status || "pending",
    emoji: getSpeciesEmoji(speciesLower),
    reason: item?.reason || ""
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
    nextItems.sort((left, right) => left.confidence - right.confidence);
  }

  return nextItems;
}
