/** Review actions for queue navigation, item status changes, undo, and loading. */
import { normalizeReviewItem } from "../../utils/helpers.js";

export function createReviewActions(app, api, stateApi, renderApi) {
  function navigateReview(direction) {
    const items = stateApi.currentItems();
    if (!items.length) return;
    app.state.reviewIndex += direction;
    if (app.state.reviewIndex < 0) app.state.reviewIndex = items.length - 1;
    if (app.state.reviewIndex >= items.length) app.state.reviewIndex = 0;
    renderApi.renderReviewQueue();
    renderApi.renderReviewViewer();
  }

  function reviewAction(action) {
    const item = stateApi.currentItems()[app.state.reviewIndex];
    if (!item) return;
    const originalStatus = item.status;
    item.status = action === "confirm" ? "confirmed" : "flagged";
    app.state.lastUndoAction = { type: "review-status", itemId: item.id, oldStatus: originalStatus };
    renderApi.showUndoToast(action === "confirm" ? "Confirmed" : "Flagged");
    renderApi.renderReviewQueue();
    renderApi.renderReviewViewer();
  }

  function undoLastAction() {
    if (!app.state.lastUndoAction) return;
    if (app.state.lastUndoAction.type === "review-status") {
      const item = app.state.reviewItems.find((entry) => entry.id === app.state.lastUndoAction.itemId);
      if (item) item.status = app.state.lastUndoAction.oldStatus;
    }
    if (app.state.lastUndoAction.type === "burst-action") {
      document.getElementById("burst-result-banner")?.classList.remove("show");
      const actions = document.getElementById("burst-action-buttons");
      if (actions) actions.style.display = "block";
    }
    app.state.lastUndoAction = null;
    renderApi.renderReviewQueue();
    renderApi.renderReviewViewer();
    app.showToast("Action undone", "success");
  }

  async function loadReviewData() {
    const container = document.getElementById("review-queue-list");
    const count = document.getElementById("queue-count");
    if (container) container.innerHTML = `<div class="review-queue-item selected"><div class="rq-file">Loading review queue…</div></div>`;
    if (count) count.textContent = "Loading…";

    try {
      const items = await api.getReviewItems();
      app.state.reviewItems = Array.isArray(items) ? items.map(normalizeReviewItem) : [];
      app.state.reviewIndex = 0;
      renderApi.renderReviewQueue();
      renderApi.renderReviewViewer();
      app.state.pageLoadState.review = true;
    } catch (error) {
      app.state.reviewItems = [];
      renderApi.renderReviewQueue();
      renderApi.renderReviewViewer();
      app.showToast(error.message || "Unable to load review items", "warn");
    }
  }

  return {
    loadReviewData,
    navigateReview,
    reviewAction,
    undoLastAction,
    undoBurstAction: undoLastAction
  };
}
