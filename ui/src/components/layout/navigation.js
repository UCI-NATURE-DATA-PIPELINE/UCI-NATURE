/** Page navigation and sidebar collapse behavior for the app shell. */
import { appState } from "../../state/appState.js";

export function bindLayoutNavigation({ showPage }) {
  document.addEventListener("click", (event) => {
    const navItem = event.target.closest(".nav-item[data-page]");
    if (navItem) {
      showPage(navItem.dataset.page);
      return;
    }

    if (event.target.closest("#collapse-btn")) {
      toggleSidebarCollapse();
    }
  });
}

export function toggleSidebarCollapse() {
  const sidebar = document.getElementById("sidebar");
  const app = document.getElementById("main-app");
  const label = document.querySelector(".collapse-label");

  appState.sidebarCollapsed = !appState.sidebarCollapsed;

  if (sidebar) {
    sidebar.classList.toggle("collapsed", appState.sidebarCollapsed);
  }
  if (app) {
    app.classList.toggle("sidebar-collapsed", appState.sidebarCollapsed);
  }
  if (label) {
    label.textContent = appState.sidebarCollapsed ? "Expand" : "Collapse";
  }
}
