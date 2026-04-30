/** Review controls for filters, species edits, and burst-review confirmation flows. */
export function createReviewControls(app, stateApi, renderApi, actionApi) {
  function askFlagConfirm() {
    app.openConfirmModal({
      title: "Flag this image?",
      body: "This image will be marked as uncertain for later review.",
      kind: "warn",
      onConfirm: () => actionApi.reviewAction("flag")
    });
  }

  function askBurstConfirm(kind) {
    const body = kind === "keep" ? "Keep only the best image from this burst group?" : "Exclude this entire burst group from export?";
    app.openConfirmModal({
      title: "Apply burst action?",
      body,
      kind: kind === "exclude" ? "danger" : "warn",
      onConfirm: () => {
        const banner = document.getElementById("burst-result-banner");
        const title = document.getElementById("burst-result-title");
        const sub = document.getElementById("burst-result-sub");
        const actions = document.getElementById("burst-action-buttons");
        if (title) title.textContent = kind === "keep" ? "Best image kept" : "Burst group excluded";
        if (sub) sub.textContent = kind === "keep" ? "Only the highest-confidence frame will be exported." : "All images in this burst group will be excluded from export.";
        if (banner) banner.classList.add("show");
        if (actions) actions.style.display = "none";
        app.state.lastUndoAction = { type: "burst-action" };
      }
    });
  }

  function openSpeciesEdit() {
    const item = stateApi.currentItems()[app.state.reviewIndex];
    if (!item) return;
    document.getElementById("species-display")?.style.setProperty("display", "none");
    document.getElementById("species-edit")?.style.setProperty("display", "block");
    const select = document.getElementById("species-select");
    if (select) select.value = item.species;
  }

  function saveSpeciesEdit() {
    const item = stateApi.currentItems()[app.state.reviewIndex];
    const select = document.getElementById("species-select");
    if (!item || !select) return;
    item.species = select.value;
    document.getElementById("species-display")?.style.setProperty("display", "flex");
    document.getElementById("species-edit")?.style.setProperty("display", "none");
    renderApi.renderReviewViewer();
    app.showToast("Species updated", "success");
  }

  return {
    askBurstConfirm,
    askFlagConfirm,
    burstAction: (kind) => {
      if (kind === "expand") app.showToast("Burst group expanded", "success");
    },
    cancelSpeciesEdit: () => {
      document.getElementById("species-display")?.style.setProperty("display", "flex");
      document.getElementById("species-edit")?.style.setProperty("display", "none");
    },
    openSpeciesEdit,
    saveSpeciesEdit,
    setRFilter: (element, value) => {
      app.state.reviewFilter = value;
      app.state.reviewIndex = 0;
      document.querySelectorAll(".rfilter-chip").forEach((chip) => chip.classList.remove("active"));
      element.classList.add("active");
      renderApi.renderReviewQueue();
      renderApi.renderReviewViewer();
    },
    toggleBurstView: () => {
      app.state.burstViewEnabled = document.getElementById("burst-toggle")?.checked ?? true;
    },
    toggleHumanFilter: (element) => {
      app.state.humanFilterOnly = !app.state.humanFilterOnly;
      element.classList.toggle("active", app.state.humanFilterOnly);
      app.state.reviewIndex = 0;
      renderApi.renderReviewQueue();
      renderApi.renderReviewViewer();
    },
    toggleSort: (button) => {
      app.state.sortMode = app.state.sortMode === "low-confidence" ? "default" : "low-confidence";
      button.innerHTML = app.state.sortMode === "low-confidence"
        ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="15" y2="12"/><line x1="3" y1="18" x2="9" y2="18"/></svg>Low confidence first`
        : `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="15" y2="12"/><line x1="3" y1="18" x2="9" y2="18"/></svg>Default order`;
      renderApi.renderReviewQueue();
      renderApi.renderReviewViewer();
    }
  };
}
