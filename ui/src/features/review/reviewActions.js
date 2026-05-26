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

  // function reviewAction(action) {
  //   const item = stateApi.currentItems()[app.state.reviewIndex];
  //   if (!item) return;
  //   const originalStatus = item.status;
  //   item.status = action === "confirm" ? "confirmed" : "flagged";
  //   app.state.lastUndoAction = { type: "review-status", itemId: item.id, oldStatus: originalStatus };
  //   renderApi.showUndoToast(action === "confirm" ? "Confirmed" : "Flagged");
  //   renderApi.renderReviewQueue();
  //   renderApi.renderReviewViewer();
  // }

  async function reviewAction(action) {
    const items = stateApi.currentItems();
    const item = items[app.state.reviewIndex];
    if (!item) return;
    
    const originalStatus = item.status;
    const newStatus = action === "confirm" ? "confirmed" : "flagged";
    const wasInFilter = true;  // the item was visible at this index
    
    // Update UI immediately for instant feedback
    item.status = newStatus;
    app.state.lastUndoAction = { type: "review-status", itemId: item.id, oldStatus: originalStatus };
    renderApi.showUndoToast(action === "confirm" ? "Confirmed" : "Flagged");
    
    // Re-fetch the filtered list after the status change
    const newItems = stateApi.currentItems();
    
    // If the item is still in the filtered list (e.g., "All" filter),
    // advance forward. Otherwise stay on the same index since items shifted up.
    const itemStillVisible = newItems.some(i => i.id === item.id);
    
    if (itemStillVisible) {
      // Item is still here (e.g., on "All" filter) → advance to next
      if (app.state.reviewIndex < newItems.length - 1) {
        app.state.reviewIndex += 1;
      }
    } else {
      // Item disappeared (e.g., on "Pending" filter) → stay at current index
      // because everything shifted up. But cap to the new list length.
      if (app.state.reviewIndex >= newItems.length) {
        app.state.reviewIndex = Math.max(0, newItems.length - 1);
      }
    }
    
    renderApi.renderReviewQueue();
    renderApi.renderReviewViewer();
    
    // Save to backend
    try {
      await api.saveReviewDecision({
        filepath: item.filepath || item.file_path || item.filename,
        reviewStatus: newStatus,
        reviewedSpecies: item.species || "",
        reviewReason: action === "flag" ? "user_flagged_uncertain" : "user_confirmed"
      });
    } catch (error) {
      item.status = originalStatus;
      renderApi.renderReviewQueue();
      renderApi.renderReviewViewer();
      app.showToast(`Failed to save decision: ${error.message}`, "warn");
    }
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

  async function proceedToValidate() {
    try {
      app.showToast("Applying review decisions to export files...", "");
      await api.applyReviewDecisions();
      app.showToast("Decisions applied. Loading export page.", "success");
      
      if (typeof window.showPage === "function") {
        window.showPage("export");
      } else if (typeof window.showPageFromReview === "function") {
        window.showPageFromReview("export");
      }
    } catch (error) {
      app.showToast(`Failed to apply decisions: ${error.message}`, "warn");
    }
  }

  return {
    proceedToValidate,
    loadReviewData,
    navigateReview,
    reviewAction,
    undoLastAction,
    undoBurstAction: undoLastAction
  };

}
