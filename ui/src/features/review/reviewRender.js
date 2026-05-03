/** Review rendering for queue rows, image viewer, and undo feedback. */
import { setHTML, setText } from "../../utils/dom.js";
import { capitalize } from "../../utils/format.js";

export function createReviewRender(app, stateApi) {
  function renderReviewQueue() {
    const container = document.getElementById("review-queue-list");
    const count = document.getElementById("queue-count");
    const completeBanner = document.getElementById("review-complete-banner");
    if (!container) return;

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
      row.innerHTML = `<div class="rq-top"><div class="rq-file">${item.filename}</div><div class="rq-confidence">${item.confidence}%</div></div><div class="rq-sub">${item.species} · ${item.camera}</div><div class="rq-status ${item.status}">${capitalize(item.status)}</div>`;
      container.appendChild(row);
    });

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
      setHTML("review-meta", `<div class="meta-row"><span class="meta-key">Source</span><span class="meta-val">speciesnet_review.csv</span></div><div class="meta-row"><span class="meta-key">Status</span><span class="meta-val">No rows returned</span></div>`);
      return;
    }

    if (app.state.reviewIndex >= items.length) app.state.reviewIndex = 0;
    const item = items[app.state.reviewIndex];
    setText("viewer-img", item.emoji);
    setText("viewer-filename", item.filename);
    setText("viewer-pos", `${app.state.reviewIndex + 1} of ${items.length}`);
    setText("nav-counter", `${app.state.reviewIndex + 1} / ${items.length}`);
    setText("conf-overlay", `${item.confidence}% confidence`);
    setText("species-name", item.species);
    setText("species-certainty", `${item.confidence}% model certainty`);
    setHTML("review-meta", `<div class="meta-row"><span class="meta-key">Filename</span><span class="meta-val">${item.filename}</span></div><div class="meta-row"><span class="meta-key">Site</span><span class="meta-val">${item.camera}</span></div><div class="meta-row"><span class="meta-key">Date / Time</span><span class="meta-val">${item.datetime}</span></div><div class="meta-row"><span class="meta-key">Burst Group</span><span class="meta-val">${item.burst}</span></div><div class="meta-row"><span class="meta-key">Status</span><span class="meta-val">${capitalize(item.status)}</span></div>`);
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
