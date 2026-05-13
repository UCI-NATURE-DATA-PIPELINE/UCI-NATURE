/** Drive feature rendering for badges, folder controls, and source summaries. */
import { appState } from "../../state/appState.js";
import { formatNumber, formatTimestampLabel } from "../../utils/format.js";
import {
  formatDriveFolderOptionLabel,
  formatDriveSyncLimitLabel,
  normalizeDriveFolderOptions
} from "../../utils/helpers.js";
import { normalizeCameraSiteName } from "./cameraSiteName.js";

export function createDriveRender(app, stateApi, utilsApi) {
  function renderDriveManualSelectionFeedback() {
    const feedbackEl = document.getElementById("drive-folder-manual-feedback");
    if (!feedbackEl) return;
    const message = appState.driveManualSelectionFeedback?.message || utilsApi.getDriveManualSelectionHint();
    const tone = appState.driveManualSelectionFeedback?.tone || "muted";
    feedbackEl.textContent = message;
    feedbackEl.style.color = tone === "success" ? "#166534" : tone === "error" ? "#B42318" : "var(--muted)";
  }

  function setDriveManualSelectionFeedback(message, tone = "muted") {
    appState.driveManualSelectionFeedback = message ? { message, tone } : null;
    renderDriveManualSelectionFeedback();
  }

  function syncDriveSelectionControls() {
    const locationEl = document.getElementById("drive-camera-location-select");
    const limitEl = document.getElementById("drive-sync-limit-select");
    const detectedEl = document.getElementById("drive-site-detected");
    const autoCardEl = document.getElementById("drive-site-auto-card");
    const helperPathEl = document.getElementById("drive-site-helper-path");
    const disabled = appState.driveSyncState.status === "syncing" || !appState.googleAuthActive || !appState.driveConnected;
    const canSync = Boolean(appState.googleAuthActive && appState.driveConnected && appState.selectedDriveFolder?.id && appState.driveSyncState.status !== "syncing");

    // Auto-detect default camera site from the selected Drive folder name.
    const detectedFromFolder = normalizeCameraSiteName(appState.selectedDriveFolder?.name || "");
    if (!appState.driveCameraLocation && detectedFromFolder) {
      appState.driveCameraLocation = detectedFromFolder;
    }

    if (locationEl) {
      syncDriveCustomSiteOption(locationEl);
      locationEl.value = appState.driveCameraLocation || "";
      locationEl.disabled = disabled;
    }
    if (detectedEl) {
      if (detectedFromFolder) {
        detectedEl.textContent = detectedFromFolder;
        detectedEl.classList.remove("muted");
        if (autoCardEl) autoCardEl.dataset.driveLocation = detectedFromFolder;
      } else {
        detectedEl.textContent = "Pick a Drive folder first";
        detectedEl.classList.add("muted");
        if (autoCardEl) autoCardEl.dataset.driveLocation = "";
      }
    }
    if (helperPathEl) {
      const label = appState.driveCameraLocation || "&lt;site&gt;";
      helperPathEl.innerHTML = `data/staging/${label}/`;
    }
    if (limitEl) {
      limitEl.value = appState.driveSyncLimit ? String(appState.driveSyncLimit) : "";
      limitEl.disabled = disabled;
    }
    const quickSyncBtn = document.getElementById("drive-sync-quick-btn");
    const syncBtn = document.getElementById("drive-sync-btn");
    const refreshStatusBtn = document.getElementById("drive-check-source-btn");
    if (quickSyncBtn) quickSyncBtn.disabled = !canSync;
    if (syncBtn) syncBtn.disabled = !canSync;
    if (refreshStatusBtn) refreshStatusBtn.disabled = !appState.googleAuthActive && !appState.selectedDriveFolder?.id;
    syncDriveCustomSiteState(disabled);
    syncDriveManualSelectionState();
    syncDriveLocationCards(disabled);
  }

  function syncDriveCustomSiteOption(selectEl) {
    // The Drive site selector is a hidden mirror of `appState.driveCameraLocation`.
    // We just clear any stale options and inject one for the current site name —
    // whether that name was auto-detected from the Drive folder or typed by the user.
    if (!selectEl) return;
    Array.from(selectEl.options)
      .filter((option) => option.value !== appState.driveCameraLocation)
      .forEach((option) => option.remove());
    if (!appState.driveCameraLocation) return;
    if (Array.from(selectEl.options).some((option) => option.value === appState.driveCameraLocation)) return;
    const customOption = document.createElement("option");
    customOption.value = appState.driveCameraLocation;
    customOption.textContent = appState.driveCameraLocation;
    customOption.dataset.driveCustom = "true";
    customOption.selected = true;
    selectEl.appendChild(customOption);
  }

  function syncDriveCustomSiteState(disabled = appState.driveSyncState.status === "syncing" || !appState.googleAuthActive || !appState.driveConnected) {
    const inputEl = document.getElementById("drive-site-custom-input");
    const buttonEl = document.getElementById("drive-site-custom-btn");
    const helperEl = document.getElementById("drive-site-helper");
    const rowEl = document.getElementById("drive-site-custom-row");
    const modalInputEl = document.getElementById("drive-site-modal-input");
    const customValueEl = document.getElementById("drive-site-custom-value");
    // Show whichever name the user is overriding to — fall back to the detected folder.
    const activeCustomSite = appState.driveCreateSiteMode && appState.driveCameraLocation
      ? appState.driveCameraLocation
      : "";
    if (inputEl) {
      inputEl.disabled = disabled;
      if (document.activeElement !== inputEl) {
        inputEl.value = activeCustomSite;
      }
    }
    if (modalInputEl && document.activeElement !== modalInputEl) {
      modalInputEl.value = activeCustomSite;
    }
    if (customValueEl) {
      if (appState.driveCreateSiteMode && appState.driveCameraLocation) {
        customValueEl.textContent = appState.driveCameraLocation;
        customValueEl.classList.remove("muted");
      } else {
        customValueEl.textContent = "No site selected";
        customValueEl.classList.add("muted");
      }
    }
    if (buttonEl) buttonEl.disabled = disabled || !String(inputEl?.value || activeCustomSite || "").trim();
    if (rowEl) rowEl.hidden = true;
    if (!helperEl) return;
    helperEl.hidden = true;
    helperEl.textContent = "";
  }

  function syncDriveLocationCards(disabled = appState.driveSyncState.status === "syncing" || !appState.googleAuthActive || !appState.driveConnected) {
    // Card-based site selection has been replaced by an auto-detected text
    // input. The querySelectorAll below is now a no-op in normal flow, but
    // we keep the function so any external caller (or a future restoration
    // of cards) won't break.
    document.querySelectorAll(".drive-loc-select-card").forEach((card) => {
      const value = String(card?.dataset?.driveLocation || "").trim();
      const cardDisabled = card?.dataset?.driveCreate === "true" ? false : disabled;
      const selected = card?.dataset?.driveCreate === "true"
        ? Boolean(appState.driveCreateSiteMode)
        : Boolean(!appState.driveCreateSiteMode && appState.driveCameraLocation && value === appState.driveCameraLocation);
      card.classList.toggle("selected", selected);
      card.classList.toggle("disabled", cardDisabled);
      card.setAttribute("aria-pressed", selected ? "true" : "false");
      card.setAttribute("aria-disabled", cardDisabled ? "true" : "false");
    });
  }

  function syncDriveManualSelectionState() {
    const inputEl = document.getElementById("drive-folder-manual-input");
    const buttonEl = document.getElementById("drive-folder-manual-btn");
    const interactive = appState.googleAuthActive && appState.driveConnected && appState.driveSyncState.status !== "syncing" && !appState.driveManualSelectionPending;
    const hasValue = Boolean(String(inputEl?.value || "").trim());
    if (inputEl) {
      inputEl.disabled = !interactive;
      inputEl.placeholder = interactive ? "https://drive.google.com/drive/folders/... or raw folder ID" : "Connect Google Drive to paste a folder URL or ID";
    }
    if (buttonEl) buttonEl.disabled = !interactive || !hasValue;
    renderDriveManualSelectionFeedback();
  }

  function setDriveFolderSelectOptions(selectEl, folders, selectedId) {
    if (!selectEl) return;
    const normalizedFolders = normalizeDriveFolderOptions(folders);
    if (!appState.googleAuthActive) {
      selectEl.innerHTML = `<option value="">Connect Google Drive to use Drive import</option>`;
      selectEl.disabled = true;
      return;
    }
    if (!appState.driveConnected) {
      selectEl.innerHTML = `<option value="">Confirm Google Drive first</option>`;
      selectEl.disabled = true;
      return;
    }
    if (appState.driveFoldersLoading) {
      selectEl.innerHTML = `<option value="">Loading Drive folders…</option>`;
      selectEl.disabled = true;
      return;
    }
    selectEl.disabled = appState.driveSyncState.status === "syncing";
    const placeholder = normalizedFolders.length
      ? "Select a Drive folder"
      : appState.driveFolderError
        ? "Drive folders unavailable"
        : "No Drive folders found";
    selectEl.innerHTML = [
      `<option value="">${placeholder}</option>`,
      ...normalizedFolders.map((folder) => `<option value="${folder.id}"${folder.id === selectedId ? " selected" : ""}>${formatDriveFolderOptionLabel(folder)}</option>`)
    ].join("");
    if (selectedId) selectEl.value = selectedId;
  }

  function updatePipelineSourceSummary() {
    const title = document.getElementById("pipeline-source-name");
    const sub = document.getElementById("pipeline-source-sub");
    if (!title || !sub) return;
    if (appState.uploadTab !== "drive") {
      title.textContent = "Local staging";
      sub.textContent = "Current local-only pipeline flow remains available";
      return;
    }

    if (!appState.selectedDriveFolder?.name) {
      title.textContent = "Google Drive: no folder selected";
      sub.textContent = appState.driveConnected ? "Select a folder on the Upload page before syncing or running the pipeline" : appState.googleAuthActive ? "Confirm Google Drive to run from a backend-selected folder" : "Connect Google Drive to run from a selected folder";
      return;
    }

    title.textContent = `Google Drive: ${appState.selectedDriveFolder.name}`;
    if (appState.driveSyncState.status === "syncing") sub.textContent = `Syncing ${formatNumber(appState.driveSyncState.downloaded_count)} of ${formatNumber(appState.driveSyncState.discovered_count || 0)} image(s) into the processing cache`;
    else if (stateApi.isDriveSourceReady()) sub.textContent = `Source ready · ${formatNumber(appState.driveSyncState.downloaded_count || appState.driveSyncState.discovered_count)} image(s) ready for processing${appState.selectedDriveFolder.id ? ` · ID ${appState.selectedDriveFolder.id}` : ""}`;
    else if (appState.driveSyncState.status === "failed") sub.textContent = appState.driveSyncState.error || "The last Drive sync failed. Run Pipeline can retry backend staging, or you can sync again first.";
    else sub.textContent = `Selected Drive folder${appState.selectedDriveFolder.id ? ` · ID ${appState.selectedDriveFolder.id}` : ""} · Run Pipeline will fetch it on the backend if needed`;
  }

  function getDriveQueuePresentation() {
    const syncStatus = appState.driveSyncState.status || "idle";
    const syncedCount = Number(appState.driveSyncState.downloaded_count || appState.driveSyncState.discovered_count || 0);
    const totalCount = Number(appState.driveSyncState.discovered_count || syncedCount || 0);
    const hasSelectedFolder = Boolean(appState.selectedDriveFolder?.name);
    const isReady = stateApi.isDriveSourceReady() || syncStatus === "completed";
    const hasAnyStagedFiles = syncedCount > 0;
    const appliedLimitLabel = formatDriveSyncLimitLabel(appState.selectedDriveFolder?.max_files ?? appState.driveSyncLimit);
    const stagingDir = appState.driveSyncState.staging_dir || "processing cache";
    const queueName = hasSelectedFolder ? appState.selectedDriveFolder.name : "No Drive folder selected";

    let queueMeta = "Pick a Drive folder above to begin.";
    if (hasSelectedFolder && !appState.googleAuthActive) queueMeta = "Google Drive source · Connect Google Drive to sync";
    else if (hasSelectedFolder && !appState.driveConnected) queueMeta = "Google Drive source · Confirm Drive connection to sync";
    else if (hasSelectedFolder) queueMeta = `Google Drive source · ${appliedLimitLabel}`;

    const queueCount = syncStatus === "syncing"
      ? `${formatNumber(Math.max(totalCount ? 2 : 1, 1))} batches · ${formatNumber(totalCount || syncedCount || 0)} files`
      : isReady || hasAnyStagedFiles
        ? `${formatNumber(Math.max(syncedCount ? 2 : 1, 1))} batches · ${formatNumber(syncedCount || totalCount || 0)} files`
        : "No sync started yet";

    const queueSize = syncStatus === "syncing" || (syncStatus === "failed" && totalCount)
      ? `${Math.max(0.1, ((syncedCount || 0) / 300).toFixed ? Number(((syncedCount || 0) / 300).toFixed(1)) : 0)} GB`
      : isReady || hasAnyStagedFiles
        ? `${Math.max(0.1, ((syncedCount || totalCount || 0) / 300).toFixed ? Number(((syncedCount || totalCount || 0) / 300).toFixed(1)) : 0)} GB`
        : "—";

    const actionText = syncStatus === "syncing"
      ? `Syncing ${formatNumber(syncedCount)} of ${formatNumber(totalCount)} files`
      : syncStatus === "failed"
        ? totalCount
          ? `Sync failed after ${formatNumber(syncedCount)} of ${formatNumber(totalCount)} files`
          : "Sync failed · refresh status or try again"
        : isReady
          ? `${formatNumber(syncedCount)} files ready for processing`
          : hasAnyStagedFiles
            ? `${formatNumber(syncedCount)} files ready · refresh status`
            : !hasSelectedFolder
              ? "No Drive folder selected · sync Drive source first"
              : !appState.googleAuthActive
                ? "Saved folder selected · sign in with Google to sync"
                : !appState.driveConnected
                  ? "Saved folder selected · confirm Drive connection to sync"
                  : "0 files ready · awaiting sync";

    const hiddenStatusSub = syncStatus === "syncing"
      ? `${formatNumber(syncedCount)} of ${formatNumber(totalCount)} image(s) synced into the ${stagingDir}`
      : syncStatus === "failed"
        ? appState.driveSyncState.error || "Retry sync or confirm the selected folder."
        : isReady
          ? `${formatNumber(syncedCount)} image(s) ready in the ${stagingDir}`
          : hasSelectedFolder
            ? `Selected folder saved with ${appliedLimitLabel}`
            : "Choose a folder, set a camera site if needed, then sync it into the processing cache.";

    const lastSyncMeta = syncStatus === "completed" && appState.driveSyncState.finished_at
      ? `Completed ${formatTimestampLabel(appState.driveSyncState.finished_at)} · ${formatNumber(syncedCount)} files ready`
      : syncStatus === "failed"
        ? appState.driveSyncState.error || "Failed. Refresh status or try again."
        : syncStatus === "syncing"
          ? `Sync in progress · ${formatNumber(syncedCount)} of ${formatNumber(totalCount)} files`
          : appState.driveSyncState.last_sync_message || "No completed Drive sync yet. Results will appear here after the first run.";

    const rawPercent = Number(appState.driveSyncState.progress_percent || 0);
    const progressPercent = Math.max(0, Math.min(100, rawPercent || (isReady ? 100 : 0)));
    const progressTone = syncStatus === "failed" ? "failed" : syncStatus === "syncing" ? "active" : isReady ? "done" : "";

    return {
      actionText,
      appliedLimitLabel,
      hiddenStatusSub,
      isReady,
      lastSyncMeta,
      progressPercent,
      progressTone,
      queueCount,
      queueMeta,
      queueName,
      queueSize,
      queueTag: appState.driveCameraLocation || "—",
      stagingDir,
      syncStatus,
      syncedCount,
      totalCount
    };
  }

  function renderDriveFolderSelection() {
    const selectEl = document.getElementById("drive-folder-select");
    const helperEl = document.getElementById("drive-folder-helper");
    const selectedNameEl = document.getElementById("drive-folder-selected-name");
    const selectedMetaEl = document.getElementById("drive-folder-selected-meta");
    const refreshBtn = document.getElementById("drive-folder-refresh-btn");
    const queuePresentation = getDriveQueuePresentation();

    setDriveFolderSelectOptions(selectEl, appState.availableDriveFolders, appState.selectedDriveFolder?.id || "");
    syncDriveSelectionControls();
    if (refreshBtn) refreshBtn.disabled = !appState.driveConnected || appState.driveFoldersLoading || appState.driveSyncState.status === "syncing";
    if (helperEl) {
      let helperText = "Choose a folder from Google Drive to continue.";
      if (!appState.googleAuthActive || !appState.driveConnected) {
        helperText = "Connect Google Drive to use Drive import.";
      } else if (appState.driveSyncState.status === "syncing") {
        helperText = `Syncing ${formatNumber(appState.driveSyncState.downloaded_count)} of ${formatNumber(appState.driveSyncState.discovered_count || 0)} image(s) from ${appState.selectedDriveFolder?.name || "the selected folder"}...`;
      } else if (appState.driveFoldersLoading) {
        helperText = "Loading folders from Google Drive…";
      } else if (appState.driveFolderError) {
        helperText = appState.driveFolderError;
      } else if (stateApi.isDriveSourceReady()) {
        helperText = `Source ready. ${formatNumber(appState.driveSyncState.downloaded_count || appState.driveSyncState.discovered_count)} image(s) are ready for processing.`;
      } else if (appState.selectedDriveFolder?.name) {
        helperText = "This folder is saved. Sync it here to prepare the remote source before processing.";
      }
      helperEl.textContent = helperText;
    }
    if (selectedNameEl) selectedNameEl.textContent = queuePresentation.queueName;
    if (selectedMetaEl) selectedMetaEl.textContent = queuePresentation.queueMeta;
    updatePipelineSourceSummary();
  }

  function syncDriveUI() {
    const driveProfile = appState.currentDriveProfile || app.features.auth.resolveDriveProfileFromBackend();
    const driveEmail = appState.googleAuthUser?.email || appState.signedInUser?.email || driveProfile.driveEmail;
    const queuePresentation = getDriveQueuePresentation();
    const syncedCount = queuePresentation.syncedCount;
    const totalCount = queuePresentation.totalCount;
    const appliedLimitLabel = queuePresentation.appliedLimitLabel;
    const driveBanner = document.getElementById("drive-sync-banner");
    if (driveBanner) {
      driveBanner.classList.toggle("connected", appState.driveConnected);
      driveBanner.classList.toggle("disconnected", !appState.driveConnected);
    }
    const summaryConnection = document.getElementById("drive-summary-connection");
    const summaryFolder = document.getElementById("drive-summary-folder");
    const summaryRange = document.getElementById("drive-summary-range");
    const summaryLimit = document.getElementById("drive-summary-limit");
    if (summaryConnection) summaryConnection.textContent = appState.driveConnected ? "Connected" : appState.googleAuthActive ? "Confirm" : "Connect Google Drive";
    if (summaryFolder) summaryFolder.textContent = appState.selectedDriveFolder?.name || "None";
    if (summaryRange) summaryRange.textContent = appState.driveCameraLocation || "—";
    if (summaryLimit) summaryLimit.textContent = appliedLimitLabel;
    const syncSummaryFolder = document.getElementById("drive-sync-summary-folder");
    const syncSummarySite = document.getElementById("drive-sync-summary-site");
    const syncSummaryLimit = document.getElementById("drive-sync-summary-limit");
    const syncSummaryDestination = document.getElementById("drive-sync-summary-destination");
    const syncSummaryConnection = document.getElementById("drive-sync-summary-connection");
    const syncSummaryStatus = document.getElementById("drive-sync-summary-status");
    const driveRuntimeWarning = document.getElementById("drive-runtime-warning");
    const destinationFolder = appState.driveCameraLocation
      ? `data/staging/${appState.driveCameraLocation}`
      : "data/staging/<camera_site>";
    const connectionStatus = appState.driveConnected ? "Connected" : appState.googleAuthActive ? "Confirm Drive" : "Connect Google Drive";
    const lastSyncStatus = queuePresentation.syncStatus === "syncing"
      ? `Syncing ${formatNumber(syncedCount)} / ${formatNumber(totalCount || syncedCount || 0)}`
      : queuePresentation.syncStatus === "failed"
        ? "Failed"
        : queuePresentation.isReady
          ? "Ready"
          : "Idle";
    if (syncSummaryFolder) syncSummaryFolder.textContent = appState.selectedDriveFolder?.name || "None";
    if (syncSummarySite) syncSummarySite.textContent = appState.driveCameraLocation || "—";
    if (syncSummaryLimit) syncSummaryLimit.textContent = appliedLimitLabel;
    if (syncSummaryDestination) syncSummaryDestination.textContent = destinationFolder;
    if (syncSummaryConnection) syncSummaryConnection.textContent = connectionStatus;
    if (syncSummaryStatus) syncSummaryStatus.textContent = lastSyncStatus;
    if (driveRuntimeWarning) {
      driveRuntimeWarning.hidden = !appState.backendHealth?.connected || Boolean(appState.backendHealth?.pipelineRuntimeReady);
    }
    document.getElementById("drive-badge")?.classList.toggle("connected", appState.driveConnected);
    document.getElementById("drive-badge")?.classList.toggle("disconnected", !appState.driveConnected);
    document.getElementById("drive-dot")?.classList.toggle("on", appState.driveConnected);
    document.getElementById("drive-dot")?.classList.toggle("off", !appState.driveConnected);
    const text = document.getElementById("drive-text");
    if (text) text.textContent = appState.driveConnected ? "Google Drive Connected" : appState.googleAuthActive ? "Confirm Google Drive" : "Connect Google Drive";
    document.getElementById("export-disconnected-banner")?.style.setProperty("display", appState.driveConnected ? "none" : "flex");
    document.getElementById("export-drive-content")?.style.setProperty("opacity", appState.driveConnected ? "1" : "0.65");
    const syncTitle = document.getElementById("drive-sync-banner-title");
    const syncSub = document.getElementById("drive-sync-banner-sub");
    if (syncTitle) syncTitle.textContent = appState.driveConnected ? "Google Drive connected" : appState.googleAuthActive ? "Confirm Google Drive" : "Google Drive not connected";
    if (syncSub) {
      syncSub.textContent = appState.driveConnected
        ? `${driveEmail} · Choose a folder, set a limit if needed, then sync.`
        : "Connect Google Drive to use Drive import.";
    }
    const queueCount = document.getElementById("drive-sync-queue-count");
    if (queueCount) queueCount.textContent = queuePresentation.queueCount;
    const selectedName = document.getElementById("drive-folder-selected-name");
    const selectedMeta = document.getElementById("drive-folder-selected-meta");
    const queueTag = document.getElementById("drive-queue-tag");
    const queueSize = document.getElementById("drive-queue-size");
    const statusText = document.getElementById("drive-sync-status-text");
    const statusTextVisible = document.getElementById("drive-sync-status-text-visible");
    const statusSub = document.getElementById("drive-sync-status-sub");
    const statusPill = document.getElementById("drive-sync-status-pill");
    const progressFill = document.getElementById("drive-sync-progress-fill");
    const progressPct = document.getElementById("drive-sync-progress-pct");
    const syncLimitSummary = document.getElementById("drive-sync-limit-summary");
    const stagingSummary = document.getElementById("drive-sync-staging-summary");
    const currentFile = document.getElementById("drive-sync-current-file");
    const syncStatus = queuePresentation.syncStatus;
    const syncPercent = queuePresentation.progressPercent;
    const usePlaceholderQueue = false;
    if (selectedName) selectedName.textContent = queuePresentation.queueName;
    if (selectedMeta) selectedMeta.textContent = queuePresentation.queueMeta;
    if (queueTag) queueTag.textContent = queuePresentation.queueTag;
    if (queueSize) queueSize.textContent = queuePresentation.queueSize;
    if (statusText) statusText.textContent = queuePresentation.actionText;
    if (statusTextVisible) {
      statusTextVisible.innerHTML = !appState.googleAuthActive || !appState.driveConnected
        ? "Connect Google Drive to use Drive import."
        : queuePresentation.isReady
          ? `<strong>${formatNumber(queuePresentation.syncedCount || queuePresentation.totalCount || 0)} files</strong> ready for processing`
          : syncStatus === "syncing"
            ? `<strong>${formatNumber(queuePresentation.syncedCount)}</strong> files synced · processing`
            : queuePresentation.actionText;
    }
    if (statusSub) statusSub.textContent = queuePresentation.hiddenStatusSub;
    if (statusPill) {
      statusPill.className = `status-pill ${usePlaceholderQueue || queuePresentation.isReady ? "pill-green" : syncStatus === "syncing" ? "pill-yellow" : syncStatus === "failed" ? "pill-red" : "pill-slate"}`;
      statusPill.textContent = usePlaceholderQueue || queuePresentation.isReady ? "✓ Complete" : syncStatus === "syncing" ? "Syncing..." : syncStatus === "failed" ? "Failed" : "Idle";
    }
    if (progressFill) {
      progressFill.className = `queue-prog-fill drive-queue-prog-fill${usePlaceholderQueue ? " done" : queuePresentation.progressTone ? ` ${queuePresentation.progressTone}` : ""}`;
      progressFill.style.setProperty("width", `${usePlaceholderQueue ? 100 : syncPercent}%`);
    }
    if (progressPct) progressPct.textContent = `${usePlaceholderQueue ? 100 : syncPercent}%`;
    if (syncLimitSummary) syncLimitSummary.textContent = appliedLimitLabel;
    if (stagingSummary) stagingSummary.textContent = `${queuePresentation.stagingDir} · ${queuePresentation.isReady ? "ready" : syncStatus === "syncing" ? "syncing" : syncStatus === "failed" ? "needs attention" : "not ready"}`;
    if (currentFile) currentFile.textContent = appState.driveSyncState.current_file || "—";
    const lastSyncTitle = document.getElementById("drive-last-sync-title");
    const lastSyncMeta = document.getElementById("drive-last-sync-meta");
    if (lastSyncTitle) lastSyncTitle.textContent = "Last Sync Result";
    if (lastSyncMeta) lastSyncMeta.textContent = queuePresentation.lastSyncMeta;
    syncDriveLocationCards();
    updatePipelineSourceSummary();
  }

  return {
    renderDriveFolderSelection,
    renderDriveManualSelectionFeedback,
    setDriveManualSelectionFeedback,
    syncDriveCustomSiteState,
    syncDriveLocationCards,
    syncDriveSelectionControls,
    syncDriveManualSelectionState,
    syncDriveUI,
    updatePipelineSourceSummary
  };
}
