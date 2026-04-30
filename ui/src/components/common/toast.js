/** Toast notifications for short success/warning UI feedback. */
export function showToast(message, type = "") {
  const container = document.getElementById("toast-container");
  if (!container) {
    return;
  }

  const toast = document.createElement("div");
  toast.className = `toast ${type}`.trim();
  toast.textContent = message;

  container.appendChild(toast);

  window.setTimeout(() => {
    toast.classList.add("show");
  }, 10);

  window.setTimeout(() => {
    toast.classList.remove("show");
    window.setTimeout(() => toast.remove(), 220);
  }, 2600);
}
