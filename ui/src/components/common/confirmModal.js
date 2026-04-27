/** Shared confirmation modal used by review and burst actions. */
let activeModalAction = null;

export function openConfirmModal({ title, body, kind, onConfirm }) {
  const overlay = document.getElementById("confirm-modal-overlay");
  const titleEl = document.getElementById("modal-title");
  const bodyEl = document.getElementById("modal-body");
  const icon = document.getElementById("modal-icon");
  const okBtn = document.getElementById("modal-ok-btn");

  activeModalAction = onConfirm || null;

  if (titleEl) titleEl.textContent = title || "Are you sure?";
  if (bodyEl) bodyEl.textContent = body || "";
  if (okBtn) okBtn.textContent = kind === "danger" ? "Confirm" : "Continue";

  if (icon) {
    icon.innerHTML = kind === "danger"
      ? `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#E53E3E" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`
      : `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#D69E2E" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
  }

  if (overlay) {
    overlay.classList.add("active");
  }
}

export function closeConfirmModal(event) {
  if (event && event.target !== event.currentTarget) {
    return;
  }
  document.getElementById("confirm-modal-overlay")?.classList.remove("active");
  activeModalAction = null;
}

export function confirmModalOK() {
  const action = activeModalAction;
  closeConfirmModal();
  if (typeof action === "function") {
    action();
  }
}
