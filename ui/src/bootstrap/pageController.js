/** App bootstrap helper for page navigation and page-specific data loading. */
export function createPageController(app) {
  function hasAppSession() {
    return Boolean(localStorage.getItem("token"));
  }

  async function loadPageData(pageName) {
    if (pageName === "upload") {
      await app.features.pipeline.loadPipelineStatus({ silent: true });
      if (app.state.driveConnected) {
        await Promise.all([
          app.features.drive.hydrateDriveFolderSelection({ silent: true }),
          app.features.drive.loadDriveSyncStatus({ silent: true })
        ]);
      }
      return;
    }

    if (pageName === "dashboard") {
      await Promise.all([
        app.features.dashboard.loadDashboardData()
      ]);
      return;
    }

    if (pageName === "review") return app.features.review.loadReviewData();
    if (pageName === "model") {
      await Promise.all([
        app.features.pipeline.loadPipelineStatus({ silent: true }),
        app.state.driveConnected ? app.features.drive.loadDriveSyncStatus({ silent: true }) : Promise.resolve(null)
      ]);
      return;
    }
    if (pageName === "validate") return;
    if (pageName === "export") return app.features.export.loadExportData({ showToastOnError: true });
  }

  async function showPage(pageName) {
    app.state.currentPage = pageName;
    document.querySelectorAll(".page").forEach((page) => page.classList.remove("active"));
    document.getElementById(`page-${pageName}`)?.classList.add("active");
    document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
    document.querySelector(`.nav-item[data-page="${pageName}"]`)?.classList.add("active");

    const titleMap = {
      dashboard: "Dashboard",
      upload: "Upload",
      model: "Run Model",
      review: "Review & Modify",
      validate: "Validate",
      export: "Export",
      statistics: "Statistics"
    };
    const titleEl = document.getElementById("page-title");
    if (titleEl) titleEl.textContent = titleMap[pageName] || "Dashboard";

    if (hasAppSession()) await loadPageData(pageName);
    if (pageName === "statistics") {
      requestAnimationFrame(() => requestAnimationFrame(() => app.features.statistics.loadStatistics()));
    }
    if (pageName !== "model" && app.state.pipelineStatus?.status !== "running") {
      app.features.pipeline.stopPipelineStatusPolling();
    }
  }

  return {
    showPage
  };
}
