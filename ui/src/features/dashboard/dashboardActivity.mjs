import { formatNumber, formatPercent, formatTimestampLabel } from "../../utils/format.js";
import { getPipelineCurrentStepLabel } from "../../utils/helpers.js";

function buildValidationIssueCount(validation) {
  return Number(validation?.outside_range || 0) +
    Number(validation?.unprocessed || 0) +
    Number(validation?.column_issue_count || 0);
}

export function buildDashboardActivityItems({
  summary,
  validation,
  exportSummary,
  pipelineStatus
} = {}) {
  const lastRun = summary?.last_run || {};
  const pipelineState = String(pipelineStatus?.status || "idle").toLowerCase();
  const issueCount = buildValidationIssueCount(validation);
  const exportFileCount = Number(exportSummary?.file_count || 0);
  const exportRows = Number(exportSummary?.total_rows || 0);
  const pendingReview = Number(summary?.pending_review || 0);
  const runId = pipelineStatus?.run_id || lastRun.batch || null;
  const currentStep = getPipelineCurrentStepLabel(pipelineStatus);
  const progressPercent = Number(pipelineStatus?.progress?.percent || 0);
  const startedAt = pipelineStatus?.started_at ? formatTimestampLabel(pipelineStatus.started_at) : null;
  const finishedAt = pipelineStatus?.finished_at ? formatTimestampLabel(pipelineStatus.finished_at) : null;

  const items = [];

  items.push({
    badge: "Pipeline",
    badgeClass:
      pipelineState === "running" ? "badge-blue" :
      pipelineState === "failed" ? "badge-red" :
      pipelineState === "completed" ? "badge-green" :
      "badge-blue",
    text:
      pipelineState === "running"
        ? `${currentStep} · ${formatPercent(progressPercent)} complete`
        : pipelineState === "failed"
          ? `Latest run failed${pipelineStatus?.error ? ` · ${pipelineStatus.error}` : ""}`
          : lastRun.date
            ? `${pipelineState === "completed" ? "Latest run completed" : "Last run"} ${lastRun.date}${lastRun.duration ? ` · ${lastRun.duration}` : ""}`
            : "No active pipeline run",
    time:
      pipelineState === "running"
        ? startedAt || `Run ${runId || "—"}`
        : pipelineState === "completed"
          ? finishedAt || `Run ${runId || "—"}`
          : runId
            ? `Run ${runId}`
            : "Idle"
  });

  items.push({
    badge: "Review",
    badgeClass: pendingReview > 0 ? "badge-yellow" : "badge-green",
    text:
      pendingReview > 0
        ? `${formatNumber(pendingReview)} item${pendingReview === 1 ? "" : "s"} waiting in review`
        : "Review queue is clear",
    time: pendingReview > 0 ? `${formatNumber(pendingReview)} open` : "Clear"
  });

  items.push({
    badge: "Validation",
    badgeClass: issueCount > 0 ? "badge-yellow" : "badge-green",
    text:
      validation
        ? issueCount > 0
          ? `${formatNumber(issueCount)} validation issue${issueCount === 1 ? "" : "s"} detected`
          : "Validation checks are clear"
        : "Validation data unavailable",
    time:
      validation
        ? `${formatNumber(Number(validation?.unprocessed || 0))} unprocessed`
        : "Not loaded"
  });

  items.push({
    badge: "Export",
    badgeClass: exportFileCount > 0 ? "badge-green" : "badge-yellow",
    text:
      exportFileCount > 0
        ? `${formatNumber(exportFileCount)} export file${exportFileCount === 1 ? "" : "s"} ready`
        : "No export artifacts available",
    time:
      exportFileCount > 0
        ? `${formatNumber(exportRows)} rows`
        : "Awaiting run"
  });

  return items;
}
