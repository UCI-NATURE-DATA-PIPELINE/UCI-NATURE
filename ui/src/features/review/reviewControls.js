/** Review controls for filters, species edits, and burst-review confirmation flows. */

const SPECIES_STORAGE_KEY = "uci_nature_species_list";
// Default species options shown in the manual-review combobox. Kept in
// the simple-label vocabulary so the review UI never displays raw model
// or taxonomy strings.
const DEFAULT_SPECIES = [
  "coyote",
  "bobcat",
  "deer",
  "raccoon",
  "rabbit",
  "skunk",
  "opossum",
  "rodent",
  "bird",
  "human",
  "dog",
  "cat",
  "vehicle",
  "blank",
  "animal_unclassified"
];

function loadSpeciesList() {
  try {
    const stored = localStorage.getItem(SPECIES_STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch (e) { /* fall through */ }
  return [...DEFAULT_SPECIES];
}

function saveSpeciesList(list) {
  try {
    localStorage.setItem(SPECIES_STORAGE_KEY, JSON.stringify(list));
  } catch (e) {
    console.warn("Failed to save species list", e);
  }
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

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

  function renderSpeciesDropdown(filterText = "") {
    const dropdown = document.getElementById("species-dropdown");
    if (!dropdown) return;
    const list = loadSpeciesList();
    const filter = filterText.trim().toLowerCase();
    const matches = filter
      ? list.filter(s => s.toLowerCase().includes(filter))
      : list;

    if (matches.length === 0) {
      dropdown.innerHTML = `<div class="species-combobox-empty">No matches. Press Enter to add "${escapeHtml(filterText)}"</div>`;
      return;
    }

    dropdown.innerHTML = matches.map(species => `
      <div class="species-combobox-option" data-species="${escapeHtml(species)}">
        <span class="species-combobox-label">${escapeHtml(species)}</span>
        <button class="species-combobox-remove" data-remove="${escapeHtml(species)}" title="Remove this species" aria-label="Remove ${escapeHtml(species)}">×</button>
      </div>
    `).join("");

    dropdown.querySelectorAll(".species-combobox-option").forEach(opt => {
      opt.addEventListener("click", (e) => {
        if (e.target.classList.contains("species-combobox-remove")) return;
        const input = document.getElementById("species-input");
        if (input) input.value = opt.dataset.species;
        hideSpeciesDropdown();
      });
    });

    dropdown.querySelectorAll(".species-combobox-remove").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const speciesToRemove = btn.dataset.remove;
        const updated = loadSpeciesList().filter(s => s !== speciesToRemove);
        saveSpeciesList(updated);
        const input = document.getElementById("species-input");
        renderSpeciesDropdown(input ? input.value : "");
      });
    });
  }

  function handleOutsideClick(e) {
    if (!e.target.closest(".species-combobox") && !e.target.closest(".review-edit-btn")) {
      hideSpeciesDropdown();
    }
  }

  function showSpeciesDropdown() {
    const dropdown = document.getElementById("species-dropdown");
    if (dropdown) dropdown.classList.add("open");
    setTimeout(() => {
      document.addEventListener("click", handleOutsideClick);
    }, 0);
  }

  function hideSpeciesDropdown() {
    const dropdown = document.getElementById("species-dropdown");
    if (dropdown) dropdown.classList.remove("open");
    document.removeEventListener("click", handleOutsideClick);
  }

  function filterSpeciesOptions() {
    const input = document.getElementById("species-input");
    if (!input) return;
    renderSpeciesDropdown(input.value);
  }

  function openSpeciesEdit() {
    const item = stateApi.currentItems()[app.state.reviewIndex];
    if (!item) return;
    document.getElementById("species-display")?.style.setProperty("display", "none");
    document.getElementById("species-edit")?.style.setProperty("display", "block");
    const input = document.getElementById("species-input");
    if (input) {
      input.value = item.species || "";
      input.focus();
      input.select(); 
      input.onkeydown = (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          const value = input.value.trim();
          if (!value) return;
          const list = loadSpeciesList();
          if (!list.some(s => s.toLowerCase() === value.toLowerCase())) {
            list.push(value);
            saveSpeciesList(list);
            app.showToast(`Added "${value}" to species list`, "success");
          }
          renderSpeciesDropdown(input.value);
        } else if (e.key === "Escape") {
          hideSpeciesDropdown();
        }
      };
    }
    document.getElementById("species-dropdown")?.classList.add("open");
    renderSpeciesDropdown("");
  }

  function saveSpeciesEdit() {
    const item = stateApi.currentItems()[app.state.reviewIndex];
    const input = document.getElementById("species-input");
    if (!item || !input) return;
    const newSpecies = input.value.trim();
    if (!newSpecies) {
      app.showToast("Please select or type a species name", "warn");
      return;
    }
    item.species = newSpecies;
    document.getElementById("species-display")?.style.setProperty("display", "flex");
    document.getElementById("species-edit")?.style.setProperty("display", "none");
    hideSpeciesDropdown();
    renderApi.renderReviewViewer();
    app.showToast("Species updated", "success");
  }

  function cancelSpeciesEdit() {
    document.getElementById("species-display")?.style.setProperty("display", "flex");
    document.getElementById("species-edit")?.style.setProperty("display", "none");
    hideSpeciesDropdown();
  }

  // document.addEventListener("click", (e) => {
  //   if (!e.target.closest(".species-combobox")) {
  //     hideSpeciesDropdown();
  //   }
  // });

  return {
    askBurstConfirm,
    askFlagConfirm,
    burstAction: (kind) => {
      if (kind === "expand") app.showToast("Burst group expanded", "success");
    },
    cancelSpeciesEdit,
    openSpeciesEdit,
    saveSpeciesEdit,
    showSpeciesDropdown,
    hideSpeciesDropdown,
    filterSpeciesOptions,
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
