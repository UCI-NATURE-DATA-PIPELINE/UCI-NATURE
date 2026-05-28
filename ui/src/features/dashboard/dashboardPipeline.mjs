const DASHBOARD_PIPELINE_STEPS = [
  { key: "upload", label: "Upload" },
  { key: "classify", label: "Classify" },
  { key: "review", label: "Review" },
  { key: "validate", label: "Validate" },
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

function resolveStageIndex(statusText, currentStepText) {
  const step = normalizeStatusText(currentStepText);
  if (!step) {
    return statusText === "completed" ? DASHBOARD_PIPELINE_STEPS.length - 1 : null;
  }

  const stageMatchers = [
    {
      key: "export",
      matchers: ["export results", "upload results", "final upload", "publish results", "export"]
    },
    {
      key: "validate",
      matchers: ["validate", "validation"]
    },
    {
      key: "review",
      matchers: ["review"]
    },
    {
      key: "classify",
      matchers: [
        "run speciesnet",
        "speciesnet",
        "postprocess",
        "parse ml",
        "inference",
        "megadetector",
        "classify"
      ]
    },
    {
      key: "upload",
      matchers: ["index drive", "download images", "manifest", "staging", "download", "ingest", "upload images"]
    }
  ];

  for (const entry of stageMatchers) {
    if (entry.matchers.some((matcher) => step.includes(matcher))) {
      return DASHBOARD_PIPELINE_STEPS.findIndex((stepItem) => stepItem.key === entry.key);
    }
  }

  return statusText === "completed" ? DASHBOARD_PIPELINE_STEPS.length - 1 : null;
}

function resolveUploadCount(status, details, totalImages) {
  return firstFiniteNumber(
    totalImages,
    status?.result?.source?.image_count,
    details?.downloaded_count,
    details?.downloaded_images,
    details?.uploaded_count,
    details?.processed_images
  );
}

function resolveProcessingCounts(details, totalImages) {
  const processedImages = firstFiniteNumber(details?.processed_images, details?.processed_count);
  const totalCount = firstFiniteNumber(details?.total_images, totalImages);
  return {
    processedImages,
    totalCount
  };
}

function buildStepCountLabel(stepKey, statusText, stepState, counts) {
  if (statusText === "idle") {
    return "—";
  }

  if (stepKey === "upload") {
    if (counts.uploadCount !== null) {
      return `${counts.uploadCount} images`;
    }
    return "—";
  }

  if (stepKey === "classify") {
    if (counts.processedImages !== null && counts.totalCount !== null) {
      return `${counts.processedImages} / ${counts.totalCount} images`;
    }
    return "—";
  }

  if (stepState === "done") {
    return "—";
  }

  if (stepState === "active") {
    return "—";
  }

  return "—";
}

function buildStepPercentLabel(stepState, progressPercent) {
  if (stepState === "done") return "100%";
  if (stepState === "active") return `${clampPercent(progressPercent)}%`;
  return "—";
}

function renderFlowPercent(statusText, stageIndex, progressPercent) {
  if (statusText === "completed") return 100;
  if (statusText !== "running" || stageIndex === null) return 0;
  const stageRatio = (stageIndex + clampPercent(progressPercent) / 100) / DASHBOARD_PIPELINE_STEPS.length;
  return clampPercent(stageRatio * 100);
}

export function buildDashboardPipelineState(status) {
  const statusText = normalizeStatusText(status?.status || "idle");
  const currentStepText = status?.progress?.step || status?.current_step || "";
  const progressPercent = clampPercent(status?.progress?.percent);
  const details = status?.progress?.details || {};
  const totalImages = firstFiniteNumber(details?.total_images, status?.result?.source?.image_count);
  const uploadCount = resolveUploadCount(status, details, totalImages);
  const processingCounts = resolveProcessingCounts(details, totalImages);
  const stageIndex = resolveStageIndex(statusText, currentStepText);
  const isRunning = statusText === "running";
  const isComplete = statusText === "completed";
  const isFailed = statusText === "failed";

  const steps = DASHBOARD_PIPELINE_STEPS.map((step, index) => {
    let stepState = "idle";
    if (isComplete) {
      stepState = "done";
    } else if (stageIndex !== null && index < stageIndex) {
      stepState = "done";
    } else if (stageIndex !== null && index === stageIndex) {
      stepState = isRunning ? "active" : "done";
    }

    return {
      key: step.key,
      label: step.label,
      state: stepState,
      percentLabel: buildStepPercentLabel(stepState, progressPercent),
      countLabel: buildStepCountLabel(step.key, statusText, stepState, {
        uploadCount,
        ...processingCounts
      })
    };
  });

  return {
    flowPercent: renderFlowPercent(statusText, stageIndex, progressPercent),
    steps
  };
}
