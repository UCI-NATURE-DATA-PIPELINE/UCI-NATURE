import {
  getPipelineDashboardMutationAt,
  getPipelineExportDownloadState
} from "../pipeline/pipelineState.js";

const DASHBOARD_PIPELINE_STEPS = [
  { key: "upload", label: "Upload" },
  { key: "classify", label: "Classify" },
  { key: "review", label: "Review" },
  { key: "export", label: "Export" }
];

function clampPercent(value) {
  const next = Number(value);
  if (!Number.isFinite(next)) return 0;
  return Math.max(0, Math.min(100, Math.round(next)));
}

function firstFiniteNumber(...values) {
  for (const value of values) {
    const next = Number(value);
    if (Number.isFinite(next) && next >= 0) return Math.round(next);
  }
  return null;
}

function normalizeStatusText(value) {
  return String(value || "").trim().toLowerCase();
}

function normalizeInputs(input) {
  if (!input) {
    return {
      pipelineStatus: null,
      uploadSnapshot: null,
      reviewSnapshot: null,
      exportSnapshot: null
    };
  }

  if (
    Object.prototype.hasOwnProperty.call(input, "pipelineStatus") ||
    Object.prototype.hasOwnProperty.call(input, "uploadSnapshot") ||
    Object.prototype.hasOwnProperty.call(input, "reviewSnapshot") ||
    Object.prototype.hasOwnProperty.call(input, "exportSnapshot")
  ) {
    return {
      pipelineStatus: input.pipelineStatus || null,
      uploadSnapshot: input.uploadSnapshot || null,
      reviewSnapshot: input.reviewSnapshot || null,
      exportSnapshot: input.exportSnapshot || null
    };
  }

  return {
    pipelineStatus: input,
    uploadSnapshot: null,
    reviewSnapshot: null,
    exportSnapshot: null
  };
}

function isCurrentRunStale(pipelineStatus, mutationAt) {
  if (!pipelineStatus || pipelineStatus.status !== "completed") return false;
  if (!mutationAt) return false;
  const finishedAt = Date.parse(pipelineStatus.finished_at || pipelineStatus.started_at || "");
  return Number.isFinite(finishedAt) && finishedAt < mutationAt;
}

function isUploadStep(stepText) {
  const step = normalizeStatusText(stepText);
  if (!step) return false;
  return [
    "sync google drive folder",
    "reuse backend cache",
    "prepare local source",
    "upload images",
    "download images",
    "index drive"
  ].some((matcher) => step.includes(matcher));
}

function isClassifyStep(stepText) {
  const step = normalizeStatusText(stepText);
  if (!step) return false;
  return [
    "run speciesnet",
    "speciesnet",
    "megadetector",
    "postprocess speciesnet",
    "parse ml results",
    "extract metadata (merge ml)",
    "generate output csvs"
  ].some((matcher) => step.includes(matcher));
}

function isReviewStep(stepText) {
  const step = normalizeStatusText(stepText);
  return step.includes("review");
}

function isExportStep(stepText) {
  const step = normalizeStatusText(stepText);
  return [
    "export results",
    "upload results",
    "final upload",
    "publish results",
    "export"
  ].some((matcher) => step.includes(matcher));
}

function getLiveClassifyCounts(status) {
  const details = status?.progress?.details || {};
  return {
    processedImages: firstFiniteNumber(details?.processed_images, details?.processed_count),
    totalCount: firstFiniteNumber(details?.total_images, status?.result?.source?.image_count)
  };
}

function buildUploadStep(pipelineStatus, uploadSnapshot, mutationAt) {
  const stale = isCurrentRunStale(pipelineStatus, mutationAt);
  const snapshotStatus = normalizeStatusText(uploadSnapshot?.status);

  if (snapshotStatus === "uploading") {
    const percent = clampPercent(uploadSnapshot?.percent);
    const done = firstFiniteNumber(uploadSnapshot?.done);
    const total = firstFiniteNumber(uploadSnapshot?.total, uploadSnapshot?.image_count);
    return {
      state: "active",
      percentLabel: `${percent}%`,
      countLabel: done !== null && total !== null ? `${done} / ${total} images` : "Uploading"
    };
  }

  if (snapshotStatus === "completed" || (pipelineStatus && pipelineStatus.status === "completed" && !stale)) {
    const totalImages = firstFiniteNumber(
      uploadSnapshot?.done,
      uploadSnapshot?.total,
      pipelineStatus?.result?.source?.image_count,
      pipelineStatus?.progress?.details?.total_images
    );
    return {
      state: "done",
      percentLabel: "100%",
      countLabel: totalImages !== null ? `${totalImages} images` : "100%"
    };
  }

  if (snapshotStatus === "failed" || snapshotStatus === "stopped") {
    return {
      state: "idle",
      percentLabel: "—",
      countLabel: "—"
    };
  }

  if (pipelineStatus && pipelineStatus.status === "running" && !stale) {
    return {
      state: "done",
      percentLabel: "100%",
      countLabel: firstFiniteNumber(
        pipelineStatus?.result?.source?.image_count,
        pipelineStatus?.progress?.details?.total_images
      ) !== null
        ? `${firstFiniteNumber(
            pipelineStatus?.result?.source?.image_count,
            pipelineStatus?.progress?.details?.total_images
          )} images`
        : "100%"
    };
  }

  return {
    state: "idle",
    percentLabel: "—",
    countLabel: "—"
  };
}

function buildClassifyStep(pipelineStatus, mutationAt) {
  if (!pipelineStatus || isCurrentRunStale(pipelineStatus, mutationAt)) {
    return {
      state: "idle",
      percentLabel: "—",
      countLabel: "—"
    };
  }

  const state = normalizeStatusText(pipelineStatus.status);
  if (state === "completed") {
    const counts = getLiveClassifyCounts(pipelineStatus);
    return {
      state: "done",
      percentLabel: "100%",
      countLabel: counts.processedImages !== null && counts.totalCount !== null
        ? `${counts.totalCount} / ${counts.totalCount} images`
        : "100%"
    };
  }

  const stepText = pipelineStatus?.progress?.step || pipelineStatus?.current_step || "";
  const counts = getLiveClassifyCounts(pipelineStatus);
  const percent = clampPercent(pipelineStatus?.progress?.percent);

  if (state === "running" && isClassifyStep(stepText)) {
    return {
      state: "active",
      percentLabel: `${percent}%`,
      countLabel: counts.processedImages !== null && counts.totalCount !== null
        ? `${counts.processedImages} / ${counts.totalCount} images`
        : "—"
    };
  }

  if (state === "running" && isExportStep(stepText)) {
    return {
      state: "done",
      percentLabel: "100%",
      countLabel: counts.processedImages !== null && counts.totalCount !== null
        ? `${counts.totalCount} / ${counts.totalCount} images`
        : "100%"
    };
  }

  if (state === "running" && !isUploadStep(stepText) && !isReviewStep(stepText)) {
    return {
      state: "done",
      percentLabel: "100%",
      countLabel: counts.processedImages !== null && counts.totalCount !== null
        ? `${counts.totalCount} / ${counts.totalCount} images`
        : "100%"
    };
  }

  return {
    state: "idle",
    percentLabel: "—",
    countLabel: "—"
  };
}

function buildReviewStep(reviewSnapshot, pipelineStatus, mutationAt) {
  const stale = isCurrentRunStale(pipelineStatus, mutationAt);
  const total = firstFiniteNumber(reviewSnapshot?.total, reviewSnapshot?.review_total);
  const reviewed = firstFiniteNumber(reviewSnapshot?.reviewed, reviewSnapshot?.done);
  const percent = clampPercent(reviewSnapshot?.percent);

  if (total !== null && reviewed !== null) {
    if (reviewed >= total) {
      return {
        state: "done",
        percentLabel: "100%",
        countLabel: `${total} / ${total} items`
      };
    }

    return {
      state: stale ? "idle" : "active",
      percentLabel: `${percent}%`,
      countLabel: `${reviewed} / ${total} items`
    };
  }

  if (pipelineStatus && pipelineStatus.status === "completed" && !stale) {
    return {
      state: "done",
      percentLabel: "100%",
      countLabel: "Reviewed"
    };
  }

  return {
    state: "idle",
    percentLabel: "—",
    countLabel: "—"
  };
}

function buildExportStep(exportSnapshot, pipelineStatus, mutationAt) {
  const state = normalizeStatusText(pipelineStatus?.status);
  const stale = isCurrentRunStale(pipelineStatus, mutationAt);
  const files = Array.isArray(exportSnapshot?.files) ? exportSnapshot.files : [];
  const ready = Boolean(exportSnapshot?.ready || files.length);
  const downloadState = exportSnapshot?.downloadState || getPipelineExportDownloadState();
  const currentRunId = String(pipelineStatus?.run_id || "").trim();
  const downloadRunId = String(downloadState?.run_id || "").trim();
  const fileName = String(downloadState?.file_name || "").trim().toLowerCase();
  const downloadedAt = Number(downloadState?.downloaded_at || 0);
  const runFinishedAt = Date.parse(pipelineStatus?.finished_at || pipelineStatus?.started_at || "");
  const isFinalDownload =
    fileName === "final_results.csv" ||
    fileName === "results.csv";

  const downloadMatchesCurrentRun =
    Boolean(currentRunId && downloadRunId && currentRunId === downloadRunId) &&
    isFinalDownload &&
    Number.isFinite(downloadedAt) &&
    downloadedAt > 0 &&
    (!Number.isFinite(runFinishedAt) || downloadedAt >= runFinishedAt) &&
    (!mutationAt || downloadedAt >= mutationAt);

  if (downloadMatchesCurrentRun && ready && state === "completed" && !stale) {
    return {
      state: "done",
      percentLabel: "100%",
      countLabel: "Downloaded"
    };
  }

  if (ready) {
    return {
      state: "idle",
      percentLabel: "Pending",
      countLabel: "Pending"
    };
  }

  return {
    state: "idle",
    percentLabel: "—",
    countLabel: "—"
  };
}

export function buildDashboardPipelineState(input) {
  const context = normalizeInputs(input);
  const pipelineStatus = context.pipelineStatus;
  const uploadSnapshot = context.uploadSnapshot;
  const reviewSnapshot = context.reviewSnapshot;
  const exportSnapshot = context.exportSnapshot;
  const mutationAt = getPipelineDashboardMutationAt();
  const currentStepText = pipelineStatus?.progress?.step || pipelineStatus?.current_step || "";

  const upload = buildUploadStep(pipelineStatus, uploadSnapshot, mutationAt);
  const classify = buildClassifyStep(pipelineStatus, mutationAt);
  const review = buildReviewStep(reviewSnapshot, pipelineStatus, mutationAt);
  const exportStep = buildExportStep(exportSnapshot, pipelineStatus, mutationAt);

  const steps = [
    { key: "upload", label: "Upload", ...upload },
    { key: "classify", label: "Classify", ...classify },
    { key: "review", label: "Review", ...review },
    { key: "export", label: "Export", ...exportStep }
  ];

  const flowPercent = steps.reduce((sum, step, index) => {
    if (step.state === "done") return sum + 25;
    if (step.state === "active") {
      const progress = clampPercent(
        index === 0
          ? uploadSnapshot?.percent
          : index === 1
            ? pipelineStatus?.progress?.percent
            : index === 2
              ? reviewSnapshot?.percent
              : 0
      );
      return sum + (progress / 100) * 25;
    }
    if (step.key === "export" && step.percentLabel === "Pending") return sum;
    return sum;
  }, 0);

  return {
    flowPercent: clampPercent(flowPercent),
    currentStep: currentStepText,
    steps
  };
}
