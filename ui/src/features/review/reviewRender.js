/** Review rendering for queue rows, image viewer, and undo feedback. */
import { setHTML, setText } from "../../utils/dom.js";
import { capitalize } from "../../utils/format.js";
import { resolveImageUrl } from "../../utils/imageUrl.js";

// Build a browser-loadable URL for a staging image referenced by a CSV row.
// The CSV stores absolute or repo-relative paths like
//   "data/staging/Test Folder/IMG_0001.JPG"
//   "data\\staging\\Test Folder\\IMG_0001.JPG"
// We slice everything after "staging/" and hand it off to resolveImageUrl(),
// which chooses the correct host:
//   - local dev (page on localhost:5500) → http://127.0.0.1:8000/images/...
//   - AWS / production (page on the duckdns host) → /images/... (same origin,
//     so Caddy proxies it to the backend container).
function getImageUrlFromPath(csvFilePath) {
  if (!csvFilePath) return "";

  // 1. Swap any Windows backslashes (\) to web forward slashes (/)
  const normalizedPath = csvFilePath.replace(/\\/g, '/');

  // 2. Cut the string perfectly right after the word "staging"
  // Using regex /staging\//i makes it case-insensitive just in case!
  const splitPath = normalizedPath.split(/staging\//i);

  const relativePath = splitPath.length > 1
    ? splitPath[1]                       // "Test Folder/WhiteScreen.jpg"
    : normalizedPath.split('/').pop();   // fallback: just the file name

  // encodeURI() converts spaces / unicode without re-encoding "/" segments.
  return resolveImageUrl(`/images/${encodeURI(relativePath)}`);
}

function getConfidenceClass(confidence) {
  // const num = Number(confidence) || 0;
  // if (num >= 70) return "high";
  // if (num >= 40) return "med";
  return "high";
}

export function createReviewRender(app, stateApi) {
  function renderReviewProgressBar() {
    const items = app.state.reviewItems || [];
    const total = items.length;
    const reviewed = items.filter(i => i.status === "confirmed" || i.status === "flagged").length;
    const remaining = total - reviewed;
    const humanCount = items.filter(i => i.humanDetected).length;
    const percent = total > 0 ? (reviewed / total) * 100 : 0;
  
    const progressFill = document.querySelector(".review-progress-bar-fill");
    if (progressFill) progressFill.style.width = `${percent}%`;
  
    const reviewedChip = document.querySelector(".review-stat-chip.blue");
    if (reviewedChip) reviewedChip.textContent = `${reviewed} / ${total} reviewed`;
  
    const remainingChip = document.querySelector(".review-stat-chip.gray");
    if (remainingChip) remainingChip.textContent = `${remaining} remaining`;
  
    const humanChip = document.getElementById("human-chip");
    if (humanChip) {
      // Preserve the icon, just update the count
      humanChip.innerHTML = `
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
          <circle cx="12" cy="7" r="4"/>
        </svg>${humanCount} Human Detection${humanCount === 1 ? "" : "s"}
      `;
    }
  }
  function renderReviewQueue() {
    const container = document.getElementById("review-queue-list");
    const count = document.getElementById("queue-count");
    const completeBanner = document.getElementById("review-complete-banner");
    if (!container) return;

    renderReviewProgressBar();

    const items = stateApi.currentItems();
    container.innerHTML = "";
    if (count) count.textContent = `${items.length} items`;

    if (!items.length) {
      container.innerHTML = `<div class="review-queue-item selected"><div class="rq-file">No review items available</div><div class="rq-sub">Current backend artifacts returned an empty review queue</div><div class="rq-status pending">Empty</div></div>`;
      if (completeBanner) completeBanner.style.display = "none";
      return;
    }

    items.forEach((item, index) => {
      const row = document.createElement("div");
      row.className = `review-queue-item ${index === app.state.reviewIndex ? "selected" : ""}`;
      row.onclick = () => {
        app.state.reviewIndex = index;
        renderReviewQueue();
        renderReviewViewer();
      };
      row.innerHTML = `
        <div class="rq-row-main">
          <div class="rq-file" title="${item.filename}">${item.filename}</div>
          <div class="rq-confidence-pill ${getConfidenceClass(item.confidence)}">${item.confidence}%</div>
        </div>
        <div class="rq-row-sub">
          <span class="rq-species">${item.species || "Unknown"}</span>
          <span class="rq-status-badge ${item.status}">${capitalize(item.status)}</span>
        </div>
      `;
      container.appendChild(row);
    });

    const selectedRow = container.children[app.state.reviewIndex];
      if (selectedRow) {
        selectedRow.scrollIntoView({
          behavior: "smooth",
          block: "nearest",
          inline: "nearest"
      });
    }

    const allDone = app.state.reviewItems.length > 0 && app.state.reviewItems.every((item) => item.status === "confirmed" || item.status === "flagged");
    if (completeBanner) completeBanner.style.display = allDone ? "block" : "none";
  }

  function renderReviewViewer() {
    const items = stateApi.currentItems();
    if (!items.length) {
      setText("viewer-img", "—");
      setText("viewer-filename", "No review items");
      setText("viewer-pos", "0 of 0");
      setText("nav-counter", "0 / 0");
      setText("conf-overlay", "0% confidence");
      setText("species-name", "Nothing pending");
      setText("species-certainty", "Review queue is empty");
      setHTML("review-meta", `<div class="meta-row"><span class="meta-key">Status</span><span class="meta-val">No items waiting for review</span></div>`);
      return;
    }

    if (app.state.reviewIndex >= items.length) app.state.reviewIndex = 0;
    const item = items[app.state.reviewIndex];
    // 1. Get the container where the emoji used to go
    const imageContainer = document.getElementById("viewer-img");

    if (imageContainer) {
      const dynamicUrl = getImageUrlFromPath(item.filepath || item.file_path || item.filename);
      
      
      imageContainer.style.display = "flex";
      imageContainer.style.alignItems = "center";
      imageContainer.style.justifyContent = "center";
      // imageContainer.style.padding = "5x"; 
      
      imageContainer.innerHTML = `<img src="${dynamicUrl}" alt="${item.species}" 
        style="width: 95%; height: 95%; object-fit: contain; 
        border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.2);" />`;
    }
    setText("viewer-filename", item.filename);
    setText("viewer-pos", `${app.state.reviewIndex + 1} of ${items.length}`);
    setText("nav-counter", `${app.state.reviewIndex + 1} / ${items.length}`);
    setText("conf-overlay", `${item.confidence}% confidence`);
    const speciesOverlay = document.getElementById("species-overlay");
    if (speciesOverlay) {
      if (item.humanDetected) {
        speciesOverlay.style.display = "none";
      } else {
        speciesOverlay.style.display = "";
        speciesOverlay.textContent = item.species || "Unknown";
      }
    }
    setText("species-name", item.species);
    setText("species-certainty", `${item.confidence}% confidence`);
    setHTML("review-meta", `<div class="meta-row"><span class="meta-key">Filename</span><span class="meta-val">${item.filename}</span></div><div class="meta-row"><span class="meta-key">Site</span><span class="meta-val">${item.camera}</span></div><div class="meta-row"><span class="meta-key">Date / Time</span><span class="meta-val">${item.datetime}</span></div><div class="meta-row"><span class="meta-key">Burst Group</span><span class="meta-val">${item.burst}</span></div><div class="meta-row"><span class="meta-key">Status</span><span class="meta-val">${capitalize(item.status)}</span></div>`);
    const detAnimal = document.getElementById("det-animal");
    if (detAnimal) {
      detAnimal.className = item.animalDetected ? "review-det-val yes" : "review-det-val no";
      detAnimal.innerHTML = item.animalDetected
        ? `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="9 12 11 14 15 10"/></svg>Yes`
        : `<span style="font-size:14px;line-height:1;font-weight:500">—</span>No`;
    }

    const detHuman = document.getElementById("det-human");
    if (detHuman) {
      detHuman.className = item.humanDetected ? "review-det-val warn" : "review-det-val no";
      detHuman.innerHTML = item.humanDetected
        ? `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="9 12 11 14 15 10"/></svg>Yes`
        : `<span style="font-size:14px;line-height:1;font-weight:500">—</span>No`;
    }
    document.getElementById("human-overlay")?.style.setProperty("display", item.humanDetected ? "inline-flex" : "none");
  }

  function showUndoToast(message) {
    const toast = document.getElementById("undo-toast");
    const label = document.getElementById("undo-toast-msg");
    if (!toast || !label) return;
    label.textContent = `✓ ${message}`;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 4000);
  }

  return {
    renderReviewQueue,
    renderReviewViewer,
    showUndoToast
  };
}
