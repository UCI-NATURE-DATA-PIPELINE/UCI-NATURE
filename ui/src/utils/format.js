/** Formatting helpers shared by page modules and presentational components. */
export function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

export function formatPercent(value) {
  return `${Math.max(0, Math.round(Number(value || 0)))}%`;
}

export function formatDecimal(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return Number(value).toFixed(2);
}

export function getPercent(part, whole) {
  if (!whole) {
    return 0;
  }
  return (Number(part || 0) / Number(whole || 0)) * 100;
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

export function formatCameraName(fileName) {
  return (fileName || "Unknown").replace(/\.csv$/i, "");
}

export function formatTimestampLabel(value) {
  if (!value) {
    return "Unknown";
  }

  try {
    return new Date(value).toLocaleString([], {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
  } catch (error) {
    return String(value);
  }
}

export function formatDurationLabel(seconds) {
  if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) {
    return "—";
  }
  const total = Math.max(0, Math.round(Number(seconds)));
  const minutes = Math.floor(total / 60);
  const remainingSeconds = total % 60;
  return `${minutes} min ${String(remainingSeconds).padStart(2, "0")} s`;
}

export function getSpeciesEmoji(species) {
  const value = (species || "").toLowerCase();
  if (value.includes("coyote")) return "🦊";
  if (value.includes("raccoon")) return "🦝";
  if (value.includes("bird")) return "🐦";
  if (value.includes("squirrel")) return "🐿️";
  if (value.includes("opossum")) return "🦡";
  if (value.includes("human")) return "🚶";
  if (value.includes("blank")) return "🖼️";
  return "🐾";
}

export function capitalize(value) {
  if (!value) {
    return "";
  }
  return value.charAt(0).toUpperCase() + value.slice(1);
}
