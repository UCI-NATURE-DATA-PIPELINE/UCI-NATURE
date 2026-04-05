function formatNumber(value) {
  if (value === null || value === undefined) return "--";
  return Number(value).toLocaleString();
}

export function renderUser(user) {
  document.getElementById("userEmail").textContent = user?.email || "--";
}

export function renderDriveStatus(driveStatus) {
  document.getElementById("driveStatusText").textContent =
    driveStatus?.connected ? "Connected" : "Not connected";
}

export function renderDashboard(data) {
  document.querySelector('[data-stat="total-images"]').textContent =
    formatNumber(data.total_images);

  document.querySelector('[data-stat="processed-images"]').textContent =
    formatNumber(data.processed_images);

  document.querySelector('[data-stat="animals-detected"]').textContent =
    formatNumber(data.animals_detected);

  document.querySelector('[data-stat="pending-review"]').textContent =
    formatNumber(data.pending_review);

  document.querySelector('[data-stat="warnings"]').textContent =
    formatNumber(data.warnings);

  document.getElementById("recentRunText").textContent =
    data.last_run_message || "No recent run data.";
}

export function renderReviewItems(items) {
  const container = document.getElementById("reviewList");
  container.innerHTML = "";

  if (!items || items.length === 0) {
    container.innerHTML = '<div class="empty-state">No review items found.</div>';
    return;
  }

  items.forEach((item) => {
    const div = document.createElement("div");
    div.className = "list-item";
    div.innerHTML = `
      <div><strong>Image:</strong> ${item.image_name || "--"}</div>
      <div><strong>Species:</strong> ${item.species || "--"}</div>
      <div><strong>Confidence:</strong> ${item.confidence ?? "--"}</div>
      <div><strong>Status:</strong> ${item.status || "--"}</div>
    `;
    container.appendChild(div);
  });
}

export function renderValidationIssues(items) {
  const container = document.getElementById("validationList");
  container.innerHTML = "";

  if (!items || items.length === 0) {
    container.innerHTML = '<div class="empty-state">No validation issues found.</div>';
    return;
  }

  items.forEach((item) => {
    const div = document.createElement("div");
    div.className = "list-item";
    div.innerHTML = `
      <div><strong>Type:</strong> ${item.issue_type || "--"}</div>
      <div><strong>Image:</strong> ${item.image_name || "--"}</div>
      <div><strong>Message:</strong> ${item.message || "--"}</div>
    `;
    container.appendChild(div);
  });
}

export function renderExportStatus(statusText) {
  document.getElementById("exportStatusBox").textContent = statusText || "No export started.";
}

export function setMessage(elementId, text, isError = false) {
  const el = document.getElementById(elementId);
  el.textContent = text;
  el.style.color = isError ? "#c53030" : "#4a5568";
}

export function showLoginScreen() {
  document.getElementById("login-screen").classList.remove("hidden");
  document.getElementById("app-shell").classList.add("hidden");
}

export function showAppShell() {
  document.getElementById("login-screen").classList.add("hidden");
  document.getElementById("app-shell").classList.remove("hidden");
}

export function updatePageHeader(page) {
  const title = document.getElementById("pageTitle");
  const subtitle = document.getElementById("pageSubtitle");

  const map = {
    dashboard: ["Dashboard", "Overview of pipeline activity and system status."],
    run: ["Run Pipeline", "Configure and start a pipeline run."],
    review: ["Review Results", "Inspect model outputs and flagged records."],
    validate: ["Validate", "View timestamp and metadata issues."],
    export: ["Export", "Export validated results."],
    settings: ["Settings", "System and project configuration."]
  };

  const [pageTitle, pageSubtitle] = map[page] || ["Dashboard", ""];
  title.textContent = pageTitle;
  subtitle.textContent = pageSubtitle;
}