import {
  loginUser,
  getCurrentUser,
  getGoogleAuthStartUrl,
  getGoogleAuthStatus,
  logoutGoogleAuth,
  connectDrive,
  getDriveStatus,
  getDriveFolders,
  saveSelectedDriveFolder,
  getSelectedDriveFolder,
  syncSelectedDriveFolder,
  getDriveSyncStatus,
  getDashboardSummary,
  runPipeline,
  getPipelineStatus,
  getReviewItems,
  getValidationIssues,
  startExport as startExportRequest
} from "./api.js";

// =========================
// GLOBAL APP STATE
// =========================
let currentPage = "dashboard";
let selectedProject = "uci";
let driveConnected = false;
let selectedFormat = "csv";
let uploadTab = "manual";
let sidebarCollapsed = false;
let uploadPaused = false;
let runningModel = false;
let exportInProgress = false;
let reviewIndex = 0;
let reviewFilter = "all";
let humanFilterOnly = false;
let burstViewEnabled = true;
let sortMode = "low-confidence";
let activeModalAction = null;
let activeDatePicker = null;
let signedInUser = null;
let currentDriveProfile = null;
let googleAuthActive = false;
let googleAuthUser = null;
let usingMockAuth = false;
let pipelineStatus = null;
let pipelineStatusPollId = null;
let availableDriveFolders = [];
let selectedDriveFolder = null;
let driveFoldersLoading = false;
let driveFolderError = "";
let driveSyncState = createEmptyDriveSyncState();
let driveSyncPollId = null;
let driveCameraLocation = "";
let driveSyncLimit = null;
const DRIVE_FOLDER_SOURCE_LABELS = {
  my_drive: "My Drive",
  shared: "Shared",
  shortcut: "Shortcut"
};
const DRIVE_MANUAL_FOLDER_HINT =
  "Paste a Google Drive folder link or raw folder ID if it doesn’t appear in the dropdown.";
let driveManualSelectionFeedback = null;
let driveManualSelectionPending = false;

const projectLabels = {
  uci: "UCI Campus Reserves",
  other: "Selected Project"
};

const driveProfiles = {
  uci: {
    driveName: "Wildlife Camera Photo Database",
    driveEmail: "julie.coffey@uci.edu",
    projectLabel: "UCI Campus Reserves"
  },
  other: {
    driveName: "Wildlife Camera Photo Database",
    driveEmail: "research.demo@uci.edu",
    projectLabel: "Selected Project"
  }
};

let reviewItems = [];
let dashboardSummary = null;
let validationData = null;
let exportData = null;
const pageLoadState = {
  dashboard: false,
  review: false,
  validate: false,
  export: false
};

let lastUndoAction = null;

// =========================
// INIT
// =========================
document.addEventListener("DOMContentLoaded", () => {
  initializeApp();
});

function initializeApp() {
  setLoginStep(1);
  updateDriveConfirmation();
  renderReviewQueue();
  renderReviewViewer();
  renderAffectedImages();
  renderUnprocessedImages();
  syncExportFilenamePreview();
  buildDatePickers();
  applyDashboardSummary(null);
  applyValidationData(null);
  applyExportData(null, null);
  applyPipelineStatus(null);
  syncDriveUI();
  renderDriveFolderSelection();
  void bootstrapAppState();
}

function hasAppSession() {
  return Boolean(signedInUser || localStorage.getItem("token"));
}

function createEmptyDriveSyncState() {
  return {
    status: "idle",
    source_ready: false,
    started_at: null,
    finished_at: null,
    folder: null,
    selected_folder: null,
    selected_folder_matches: false,
    discovered_count: 0,
    downloaded_count: 0,
    remaining_count: 0,
    progress_percent: 0,
    current_file: null,
    staging_dir: null,
    drive_index_path: null,
    error: null,
    last_sync_message: null
  };
}

function normalizeDriveSyncStatus(value) {
  const next = {
    ...createEmptyDriveSyncState(),
    ...(value || {})
  };

  next.folder = next.folder || null;
  next.selected_folder = next.selected_folder || null;
  next.status = String(next.status || "idle").toLowerCase();
  next.discovered_count = Number(next.discovered_count || 0);
  next.downloaded_count = Number(next.downloaded_count || 0);
  next.remaining_count = Number(
    next.remaining_count != null
      ? next.remaining_count
      : Math.max(next.discovered_count - next.downloaded_count, 0)
  );
  next.progress_percent = Number(
    next.progress_percent != null
      ? next.progress_percent
      : next.discovered_count
        ? Math.round((next.downloaded_count / next.discovered_count) * 100)
        : next.status === "completed"
          ? 100
          : 0
  );
  next.selected_folder_matches = Boolean(
    next.selected_folder_matches != null
      ? next.selected_folder_matches
      : next.folder?.id && next.selected_folder?.id && next.folder.id === next.selected_folder.id
  );
  next.source_ready = Boolean(next.source_ready && next.selected_folder_matches);
  return next;
}

function normalizeDriveSyncLimitValue(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null;
}

function formatDriveSyncLimitLabel(value) {
  const normalized = normalizeDriveSyncLimitValue(value);
  return normalized ? `First ${formatNumber(normalized)} files` : "All files";
}

function applySelectedDriveFolderSettings(folder = null) {
  driveCameraLocation = String(folder?.camera_location || "");
  driveSyncLimit = normalizeDriveSyncLimitValue(folder?.max_files);
}

function syncDriveSelectionControls() {
  const locationEl = document.getElementById("drive-camera-location-select");
  const limitEl = document.getElementById("drive-sync-limit-select");
  const controlsDisabled =
    driveSyncState.status === "syncing" ||
    !googleAuthActive ||
    !driveConnected;

  if (locationEl) {
    locationEl.value = driveCameraLocation || "";
    locationEl.disabled = controlsDisabled;
  }

  if (limitEl) {
    limitEl.value = driveSyncLimit ? String(driveSyncLimit) : "";
    limitEl.disabled = controlsDisabled;
  }
}

function applyDriveSyncStatus(value) {
  driveSyncState = normalizeDriveSyncStatus(value);
  syncDriveUI();
  renderDriveFolderSelection();
}

function isDriveSourceReady() {
  return Boolean(
    driveConnected &&
    selectedDriveFolder?.id &&
    driveSyncState.source_ready &&
    driveSyncState.folder?.id === selectedDriveFolder.id
  );
}

function canRunDrivePipeline() {
  return Boolean(
    googleAuthActive &&
    driveConnected &&
    selectedDriveFolder?.id &&
    driveSyncState.status !== "syncing"
  );
}

function getDriveSyncStepPercent() {
  const explicitPercent = Number(pipelineStatus?.progress?.percent);
  if (Number.isFinite(explicitPercent) && explicitPercent >= 0) {
    return Math.max(0, Math.min(100, explicitPercent));
  }

  const step = (pipelineStatus?.current_step || "").toLowerCase();

  if (!step) return runningModel ? 8 : 0;
  if (step.includes("create manifest")) return 15;
  if (step.includes("extract metadata (exif)")) return 28;
  if (step.includes("run speciesnet")) return 55;
  if (step.includes("postprocess speciesnet")) return 70;
  if (step.includes("parse ml results")) return 82;
  if (step.includes("extract metadata (merge ml)")) return 90;
  if (step.includes("generate output csvs")) return 96;
  return runningModel ? 12 : 0;
}

function getDriveRunIdleNote() {
  if (!googleAuthActive) {
    return "Sign in with Google to sync a Drive folder. Local mode still works separately.";
  }

  if (!driveConnected) {
    return "Confirm the Google Drive connection to use the Drive-backed flow.";
  }

  if (!selectedDriveFolder?.id) {
    return "Select a Google Drive folder on this page before syncing.";
  }

  if (driveSyncState.status === "syncing") {
    return `Syncing ${formatNumber(driveSyncState.downloaded_count)} of ${formatNumber(driveSyncState.discovered_count || 0)} image(s) into the backend staging cache...`;
  }

  if (driveSyncState.status === "failed") {
    return driveSyncState.error || "The last Drive sync failed. Run Pipeline will retry backend staging, or you can sync again first.";
  }

  if (isDriveSourceReady()) {
    return `Source ready: ${formatNumber(driveSyncState.downloaded_count || driveSyncState.discovered_count)} staged image(s) from ${selectedDriveFolder.name}. Run Pipeline can reuse this backend cache.`;
  }

  return "Run Pipeline will fetch and stage the selected Drive folder on the backend server. Sync is optional if you want to pre-stage the cache first.";
}

function getDriveManualSelectionHint() {
  if (!googleAuthActive) {
    return "Sign in with Google before pasting a folder URL or ID.";
  }

  if (!driveConnected) {
    return "Confirm the Google Drive connection before pasting a folder URL or ID.";
  }

  if (driveSyncState.status === "syncing") {
    return "Wait for the current Drive sync to finish before changing folders.";
  }

  return DRIVE_MANUAL_FOLDER_HINT;
}

function renderDriveManualSelectionFeedback() {
  const feedbackEl = document.getElementById("drive-folder-manual-feedback");
  if (!feedbackEl) return;

  const message = driveManualSelectionFeedback?.message || getDriveManualSelectionHint();
  const tone = driveManualSelectionFeedback?.tone || "muted";
  const color = tone === "success"
    ? "#166534"
    : tone === "error"
      ? "#B42318"
      : "var(--muted)";

  feedbackEl.textContent = message;
  feedbackEl.style.color = color;
}

function setDriveManualSelectionFeedback(message, tone = "muted") {
  driveManualSelectionFeedback = message
    ? { message, tone }
    : null;
  renderDriveManualSelectionFeedback();
}

function syncDriveManualSelectionState() {
  const inputEl = document.getElementById("drive-folder-manual-input");
  const buttonEl = document.getElementById("drive-folder-manual-btn");
  const isInteractive = (
    googleAuthActive &&
    driveConnected &&
    driveSyncState.status !== "syncing" &&
    !driveManualSelectionPending
  );
  const hasValue = Boolean(String(inputEl?.value || "").trim());

  if (inputEl) {
    inputEl.disabled = !isInteractive;
    inputEl.placeholder = isInteractive
      ? "https://drive.google.com/drive/folders/... or raw folder ID"
      : "Connect Google Drive to paste a folder URL or ID";
  }

  if (buttonEl) {
    buttonEl.disabled = !isInteractive || !hasValue;
  }

  renderDriveManualSelectionFeedback();
}

function updateDriveSyncPollingState() {
  if (driveSyncState.status === "syncing") {
    startDriveSyncPolling();
  } else {
    stopDriveSyncPolling();
  }
}

async function loadDriveSyncStatus({ silent = false } = {}) {
  if (!hasAppSession()) {
    applyDriveSyncStatus(null);
    stopDriveSyncPolling();
    return driveSyncState;
  }

  try {
    const sync = await getDriveSyncStatus();
    applyDriveSyncStatus(sync);
    updateDriveSyncPollingState();
    return sync;
  } catch (error) {
    if (!silent) {
      showToast(error.message || "Unable to load Drive sync status", "warn");
    }
    return driveSyncState;
  }
}

function startDriveSyncPolling() {
  if (driveSyncPollId) return;
  driveSyncPollId = window.setInterval(() => {
    void loadDriveSyncStatus({ silent: true });
  }, 1200);
}

function stopDriveSyncPolling() {
  if (!driveSyncPollId) return;
  window.clearInterval(driveSyncPollId);
  driveSyncPollId = null;
}

// =========================
// PAGE / NAV
// =========================
function showPage(pageName) {
  currentPage = pageName;

  document.querySelectorAll(".page").forEach((page) => {
    page.classList.remove("active");
  });

  const targetPage = document.getElementById(`page-${pageName}`);
  if (targetPage) targetPage.classList.add("active");

  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.remove("active");
  });

  const activeNav = document.querySelector(`.nav-item[data-page="${pageName}"]`);
  if (activeNav) activeNav.classList.add("active");

  const titleMap = {
    dashboard: "Dashboard",
    upload: "Upload",
    model: "Run Model",
    review: "Review & Modify",
    validate: "Validate",
    export: "Export"
  };

  const titleEl = document.getElementById("page-title");
  if (titleEl) titleEl.textContent = titleMap[pageName] || "Dashboard";

  if (hasAppSession()) {
    void loadPageData(pageName);
  }

  if (pageName !== "model" && pipelineStatus?.status !== "running") {
    stopPipelineStatusPolling();
  }
}

function showPageFromReview(pageName) {
  showPage(pageName);
}

// =========================
// LOGIN FLOW
// =========================
function selectProject(cardEl) {
  document.querySelectorAll(".project-card").forEach((card) => {
    if (!card.classList.contains("disabled")) {
      card.classList.remove("selected");
    }
  });

  cardEl.classList.add("selected");
  selectedProject = cardEl.id === "proj-uci" ? "uci" : "other";
  currentDriveProfile = null;
  updateDriveConfirmation();
}

function setLoginStep(step) {
  const s1 = document.getElementById("login-step1");
  const s2 = document.getElementById("login-step2");
  const l1 = document.getElementById("lstep-1");
  const l2 = document.getElementById("lstep-2");
  const l3 = document.getElementById("lstep-3");

  if (s1) s1.style.display = step === 1 ? "block" : "none";
  if (s2) s2.style.display = step === 2 || step === 3 ? "block" : "none";

  [l1, l2, l3].forEach((el) => {
    if (el) el.classList.remove("active", "done");
  });

  if (step === 1) {
    if (l1) l1.classList.add("active");
  } else if (step === 2) {
    if (l1) l1.classList.add("done");
    if (l2) l2.classList.add("active");
  } else if (step === 3) {
    if (l1) l1.classList.add("done");
    if (l2) l2.classList.add("done");
    if (l3) l3.classList.add("active");
  }
}

function goToStep1() {
  setLoginStep(1);
}

function goToStep2() {
  setLoginStep(2);
}

function goToStep3() {
  setLoginStep(3);
}

// Bind login actions early so inline handlers remain available even if a later
// runtime error prevents the final window-binding block from running.
window.selectProject = selectProject;
window.goToStep1 = goToStep1;
window.goToStep2 = goToStep2;
window.goToStep3 = goToStep3;

function getDriveProfile() {
  return driveProfiles[selectedProject] || {
    driveName: "Wildlife Camera Photo Database",
    driveEmail: "wildlife.demo@uci.edu",
    projectLabel: projectLabels[selectedProject] || "Selected Project"
  };
}

function resolveDriveProfileFromBackend(driveStatus = null) {
  const fallbackProfile = getDriveProfile();

  return {
    ...fallbackProfile,
    driveName:
      driveStatus?.drive_name ||
      currentDriveProfile?.driveName ||
      fallbackProfile.driveName,
    driveEmail:
      driveStatus?.drive_email ||
      googleAuthUser?.email ||
      signedInUser?.email ||
      currentDriveProfile?.driveEmail ||
      fallbackProfile.driveEmail
  };
}

function applyBackendDriveState(googleAuth = null, driveStatus = null) {
  googleAuthActive = Boolean(googleAuth?.authenticated);
  googleAuthUser = googleAuth?.user || null;
  driveConnected = googleAuthActive && Boolean(driveStatus?.connected);
  selectedDriveFolder = driveStatus?.selected_folder || selectedDriveFolder || null;
  applySelectedDriveFolderSettings(selectedDriveFolder);
  driveSyncState = normalizeDriveSyncStatus(driveStatus?.sync || driveSyncState);
  currentDriveProfile = resolveDriveProfileFromBackend(driveStatus);
}

function updateDriveConfirmation() {
  currentDriveProfile = resolveDriveProfileFromBackend();

  const title = document.getElementById("drive-modal-title");
  const sub = document.getElementById("drive-modal-sub");
  const name = document.getElementById("drive-confirm-name");
  const account = document.getElementById("drive-confirm-account");
  const confirmBtn = document.getElementById("drive-confirm-btn");

  const userEmail = googleAuthUser?.email || signedInUser?.email || currentDriveProfile.driveEmail;

  if (title) {
    title.textContent = googleAuthActive ? "Confirm Drive Connection" : "Connect Google Drive";
  }
  if (sub) {
    sub.textContent = googleAuthActive
      ? "We found the following Google Drive. Please confirm this is the correct project drive before continuing."
      : "Sign in with the Google account that can access this project folder. Local mode remains available without Drive.";
  }
  if (name) name.textContent = currentDriveProfile.driveName;
  if (account) {
    account.textContent = googleAuthActive
      ? `${userEmail} · ${currentDriveProfile.projectLabel}`
      : `${currentDriveProfile.projectLabel} · Not signed in`;
  }
  if (confirmBtn) {
    confirmBtn.textContent = googleAuthActive ? "Confirm & Enter Dashboard" : "Sign in with Google first";
    confirmBtn.disabled = !googleAuthActive;
  }
}

function setDriveModalVisible(isVisible) {
  const modal = document.getElementById("drive-modal");
  if (modal) modal.classList.toggle("visible", isVisible);
}

async function simulateOAuth() {
  const oauthBtn = document.getElementById("oauth-btn");
  const originalText = oauthBtn?.innerHTML;

  goToStep3();
  if (oauthBtn) {
    oauthBtn.disabled = true;
    oauthBtn.textContent = "Signing in...";
  }

  currentDriveProfile = getDriveProfile();
  usingMockAuth = false;

  try {
    const response = await loginUser(currentDriveProfile.driveEmail, selectedProject);
    const sessionToken = String(response?.access_token || "").trim();
  if (sessionToken) {
  localStorage.setItem("token", sessionToken);
    }
    const authUrl = await getGoogleAuthStartUrl(sessionToken);
    
    signedInUser = response?.user || null;
    googleAuthActive = false;
    googleAuthUser = null;
    updateDriveConfirmation();
    if (!authUrl) {
      throw new Error("Google OAuth start URL was not returned by the backend");
    }
    window.location.assign(authUrl);
    return;
  } catch (error) {
    localStorage.removeItem("token");
    signedInUser = null;
    googleAuthActive = false;
    googleAuthUser = null;
    showToast(error.message || "Unable to start Google sign-in", "warn");
    setLoginStep(2);
  } finally {
    if (oauthBtn) {
      oauthBtn.innerHTML = originalText;
      oauthBtn.disabled = false;
    }
  }
}

async function confirmDrive() {
  if (!googleAuthActive) {
    showToast("Sign in with Google before confirming Drive", "warn");
    return;
  }

  currentDriveProfile = getDriveProfile();

  try {
    const response = await connectDrive(
      currentDriveProfile.driveName,
      signedInUser?.email || currentDriveProfile.driveEmail
    );
    driveConnected = googleAuthActive && Boolean(response?.connected);
    currentDriveProfile = resolveDriveProfileFromBackend({
      drive_name: response?.drive_name,
      drive_email: response?.drive_email,
      selected_folder: response?.selected_folder
    });
    selectedDriveFolder = response?.selected_folder || selectedDriveFolder;
    usingMockAuth = false;
    setDriveManualSelectionFeedback(null);
    syncDriveUI();
    await hydrateDriveFolderSelection({ silent: true });
    enterDashboard();
    switchUploadTab("drive");
    showPage("upload");
    showToast("Google Drive connected. Pick a folder to continue.", "success");
  } catch (error) {
    driveConnected = false;
    syncDriveUI();
    showToast(error.message || "Google Drive confirmation failed", "warn");
  }
}

async function switchAccount() {
  try {
    await logoutGoogleAuth();
  } catch (error) {
    // Keep the UI reset path usable even if the backend session is already gone.
  }

  driveConnected = false;
  signedInUser = null;
  currentDriveProfile = null;
  googleAuthActive = false;
  googleAuthUser = null;
  usingMockAuth = false;
  selectedDriveFolder = null;
  applySelectedDriveFolderSettings(null);
  availableDriveFolders = [];
  driveFoldersLoading = false;
  driveFolderError = "";
  driveSyncState = createEmptyDriveSyncState();
  driveManualSelectionFeedback = null;
  driveManualSelectionPending = false;
  stopDriveSyncPolling();
  localStorage.removeItem("token");
  setDriveModalVisible(false);
  setLoginStep(2);
  updateDriveConfirmation();
  syncDriveUI();
  renderDriveFolderSelection();
}

function openDriveModal() {
  if (!googleAuthActive) {
    returnToLogin();
    setLoginStep(2);
    updateDriveConfirmation();
    return;
  }

  updateDriveConfirmation();
  setDriveModalVisible(true);
}

function reconnectDrive() {
  openDriveModal();
}

window.simulateOAuth = simulateOAuth;
window.confirmDrive = confirmDrive;
window.switchAccount = switchAccount;
window.openDriveModal = openDriveModal;
window.reconnectDrive = reconnectDrive;

// =========================
// DRIVE UI
// =========================
function syncDriveUI() {
  const badge = document.getElementById("drive-badge");
  const dot = document.getElementById("drive-dot");
  const text = document.getElementById("drive-text");
  const exportBanner = document.getElementById("export-disconnected-banner");
  const exportContent = document.getElementById("export-drive-content");
  const syncBanner = document.getElementById("drive-sync-banner");
  const syncTitle = document.getElementById("drive-sync-banner-title");
  const syncSub = document.getElementById("drive-sync-banner-sub");
  const reconnectBtn = document.getElementById("drive-sync-reconnect-btn");
  const driveProfile = currentDriveProfile || resolveDriveProfileFromBackend();
  const driveEmail = googleAuthUser?.email || signedInUser?.email || driveProfile.driveEmail;
  const selectedFolderName = selectedDriveFolder?.name || "";
  const syncedCount = driveSyncState.downloaded_count || driveSyncState.discovered_count || 0;
  const totalCount = driveSyncState.discovered_count || syncedCount;
  const appliedLimitLabel = formatDriveSyncLimitLabel(selectedDriveFolder?.max_files ?? driveSyncLimit);
  const lastSyncTitle = document.getElementById("drive-last-sync-title");
  const lastSyncMeta = document.getElementById("drive-last-sync-meta");
  const queueCount = document.getElementById("drive-sync-queue-count");
  const queueStatusPill = document.getElementById("drive-sync-status-pill");
  const queueStatusText = document.getElementById("drive-sync-status-text");
  const queueStatusSub = document.getElementById("drive-sync-status-sub");
  const queueFill = document.getElementById("drive-sync-progress-fill");
  const queuePct = document.getElementById("drive-sync-progress-pct");
  const syncLimitSummary = document.getElementById("drive-sync-limit-summary");
  const syncStagingSummary = document.getElementById("drive-sync-staging-summary");
  const syncCurrentFile = document.getElementById("drive-sync-current-file");
  const driveRunBtn = document.getElementById("drive-run-btn");
  const driveRunNote = document.getElementById("drive-run-note");
  const stagingPath = driveSyncState.staging_dir || "data/staging";

  if (driveConnected) {
    if (badge) {
      badge.classList.remove("disconnected");
      badge.classList.add("connected");
    }
    if (dot) {
      dot.classList.remove("off");
      dot.classList.add("on");
    }
    if (text) text.textContent = "Google Drive Connected";

    if (exportBanner) exportBanner.style.display = "none";
    if (exportContent) exportContent.style.opacity = "1";

    if (syncBanner) {
      syncBanner.classList.add("connected");
      syncBanner.classList.remove("disconnected");
    }
    if (syncTitle) syncTitle.textContent = `Connected — ${driveProfile.driveName}`;
    if (syncSub) {
      syncSub.textContent = `${driveEmail} · Select a folder and sync settings below`;
    }
    if (reconnectBtn) reconnectBtn.style.display = "none";
  } else {
    if (badge) {
      badge.classList.add("disconnected");
      badge.classList.remove("connected");
    }
    if (dot) {
      dot.classList.add("off");
      dot.classList.remove("on");
    }
    if (text) {
      text.textContent = googleAuthActive ? "Confirm Google Drive" : "Connect Google Drive";
    }

    if (exportBanner) exportBanner.style.display = "flex";
    if (exportContent) exportContent.style.opacity = "0.65";

    if (syncBanner) {
      syncBanner.classList.remove("connected");
      syncBanner.classList.add("disconnected");
    }
    if (syncTitle) {
      syncTitle.textContent = googleAuthActive ? "Google account connected" : "Google Drive not connected";
    }
    if (syncSub) {
      syncSub.textContent = selectedFolderName
        ? `${googleAuthActive ? "Confirm this Drive connection to use the saved folder." : "Sign in with Google again to use the saved folder."}`
        : googleAuthActive
          ? `${driveEmail} · Confirm this Drive connection to enable folder staging`
          : "Sign in with Google to sync image folders. Manual mode still works.";
    }
    if (reconnectBtn) {
      reconnectBtn.style.display = "inline-flex";
      reconnectBtn.textContent = googleAuthActive ? "Confirm Drive" : "Reconnect";
    }
  }

  if (queueCount) {
    if (driveSyncState.status === "syncing" || totalCount) {
      queueCount.textContent = `${formatNumber(syncedCount)} / ${formatNumber(totalCount || 0)} staged`;
    } else if (selectedFolderName) {
      queueCount.textContent = appliedLimitLabel;
    } else {
      queueCount.textContent = "Awaiting folder sync";
    }
  }

  if (queueStatusPill) {
    queueStatusPill.className = "status-pill";
    if (driveSyncState.status === "completed" && isDriveSourceReady()) {
      queueStatusPill.classList.add("pill-green");
      queueStatusPill.textContent = "Ready";
    } else if (driveSyncState.status === "syncing") {
      queueStatusPill.classList.add("pill-yellow");
      queueStatusPill.textContent = "Syncing";
    } else if (driveSyncState.status === "failed") {
      queueStatusPill.classList.add("pill-red");
      queueStatusPill.textContent = "Failed";
    } else {
      queueStatusPill.classList.add("pill-slate");
      queueStatusPill.textContent = "Idle";
    }
  }

  if (queueStatusText) {
    if (driveSyncState.status === "syncing") {
      queueStatusText.textContent = `Syncing ${selectedFolderName || "selected folder"} into backend staging`;
    } else if (isDriveSourceReady()) {
      queueStatusText.textContent = "Drive source ready";
    } else if (driveSyncState.status === "failed") {
      queueStatusText.textContent = "Drive sync failed";
    } else if (selectedFolderName) {
      queueStatusText.textContent = "Selected folder saved";
    } else {
      queueStatusText.textContent = "Sync a Drive folder to prepare the source";
    }
  }

  if (queueStatusSub) {
    if (driveSyncState.status === "syncing") {
      queueStatusSub.textContent = `${formatNumber(syncedCount)} of ${formatNumber(totalCount || 0)} files downloaded · ${appliedLimitLabel}`;
    } else if (isDriveSourceReady()) {
      queueStatusSub.textContent = `${formatNumber(syncedCount)} file(s) staged in ${stagingPath} · ${appliedLimitLabel}`;
    } else if (driveSyncState.status === "failed") {
      queueStatusSub.textContent = driveSyncState.error || "Retry sync to prepare the Drive source.";
    } else if (selectedFolderName) {
      queueStatusSub.textContent = `Sync will stage files into ${stagingPath}. Run Pipeline can also fetch the folder on demand.`;
    } else {
      queueStatusSub.textContent = "Choose a folder, optionally set a camera location or sync limit, then sync or run the pipeline.";
    }
  }

  if (queueFill) {
    queueFill.style.width = `${Math.max(0, Math.min(100, driveSyncState.progress_percent || 0))}%`;
  }
  if (queuePct) {
    queuePct.textContent = `${Math.max(0, Math.min(100, driveSyncState.progress_percent || 0))}%`;
  }

  if (syncLimitSummary) {
    syncLimitSummary.textContent = appliedLimitLabel;
  }
  if (syncStagingSummary) {
    syncStagingSummary.textContent = isDriveSourceReady()
      ? `${stagingPath} · drive_index.csv ready`
      : driveSyncState.status === "syncing"
        ? `${stagingPath} · downloading`
        : `${stagingPath} · not staged yet`;
  }
  if (syncCurrentFile) {
    syncCurrentFile.textContent = driveSyncState.current_file || "—";
  }

  if (lastSyncTitle) {
    if (driveSyncState.status === "completed" && driveSyncState.finished_at) {
      lastSyncTitle.textContent = `Last sync completed ${formatTimestampLabel(driveSyncState.finished_at)}`;
    } else if (driveSyncState.status === "failed") {
      lastSyncTitle.textContent = "Last sync failed";
    } else if (driveSyncState.status === "syncing") {
      lastSyncTitle.textContent = "Sync in progress";
    } else {
      lastSyncTitle.textContent = "No completed Drive sync yet";
    }
  }
  if (lastSyncMeta) {
    if (driveSyncState.status === "completed") {
      lastSyncMeta.textContent = `${formatNumber(syncedCount)} image(s) staged on the backend · ${appliedLimitLabel}${driveSyncState.drive_index_path ? ` · ${driveSyncState.drive_index_path}` : ""}`;
    } else if (driveSyncState.status === "failed") {
      lastSyncMeta.textContent = driveSyncState.error || "Retry sync to prepare this folder.";
    } else {
      lastSyncMeta.textContent = driveSyncState.last_sync_message || "Sync results will appear here after the first run.";
    }
  }

  if (driveRunBtn) {
    driveRunBtn.disabled = runningModel || !canRunDrivePipeline();
  }
  if (driveRunNote && (!pipelineStatus || pipelineStatus.status === "idle")) {
    driveRunNote.textContent = getDriveRunIdleNote();
  }

  updatePipelineSourceSummary();
}

function setDriveFolderSelectOptions(selectEl, folders, selectedId) {
  if (!selectEl) return;
  const normalizedFolders = normalizeDriveFolderOptions(folders);

  if (!googleAuthActive) {
    selectEl.innerHTML = `<option value="">Sign in with Google first</option>`;
    selectEl.disabled = true;
    return;
  }

  if (!driveConnected) {
    selectEl.innerHTML = `<option value="">Confirm Google Drive first</option>`;
    selectEl.disabled = true;
    return;
  }

  if (driveFoldersLoading) {
    selectEl.innerHTML = `<option value="">Loading Drive folders…</option>`;
    selectEl.disabled = true;
    return;
  }

  if (driveSyncState.status === "syncing") {
    selectEl.disabled = true;
  }

  if (!normalizedFolders.length) {
    const emptyLabel = driveFolderError
      ? "Drive folders unavailable"
      : "No Drive folders found";
    selectEl.innerHTML = `<option value="">${escapeHtml(emptyLabel)}</option>`;
    selectEl.disabled = true;
    return;
  }

  selectEl.disabled = driveSyncState.status === "syncing";
  selectEl.innerHTML = [
    `<option value="">Select a Google Drive folder</option>`,
    ...normalizedFolders.map((folder) => `
      <option value="${escapeHtml(folder.id)}"${folder.id === selectedId ? " selected" : ""}>
        ${escapeHtml(formatDriveFolderOptionLabel(folder))}
      </option>
    `)
  ].join("");

  if (selectedId) {
    selectEl.value = selectedId;
  }
}

function normalizeDriveFolderOptions(folders) {
  if (!Array.isArray(folders)) {
    return [];
  }

  const seen = new Set();
  const normalized = [];

  folders.forEach((folder) => {
    const id = String(folder?.id || "").trim();
    const name = String(folder?.name || "").trim();
    if (!id || !name || seen.has(id)) {
      return;
    }

    const source = String(folder?.source || "").trim().toLowerCase();
    normalized.push({
      ...folder,
      id,
      name,
      source: source || "my_drive"
    });
    seen.add(id);
  });

  normalized.sort((a, b) => {
    const nameCompare = a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
    if (nameCompare !== 0) {
      return nameCompare;
    }

    const sourceA = DRIVE_FOLDER_SOURCE_LABELS[a.source] || a.source || "";
    const sourceB = DRIVE_FOLDER_SOURCE_LABELS[b.source] || b.source || "";
    const sourceCompare = sourceA.localeCompare(sourceB, undefined, { sensitivity: "base" });
    if (sourceCompare !== 0) {
      return sourceCompare;
    }

    return a.id.localeCompare(b.id);
  });

  return normalized;
}

function formatDriveFolderOptionLabel(folder) {
  const label = String(folder?.name || "").trim();
  const sourceKey = String(folder?.source || "").trim().toLowerCase();
  const sourceLabel = DRIVE_FOLDER_SOURCE_LABELS[sourceKey] || "";

  return sourceLabel && sourceKey !== "my_drive"
    ? `${label} (${sourceLabel})`
    : label;
}

function updatePipelineSourceSummary() {
  const title = document.getElementById("pipeline-source-name");
  const sub = document.getElementById("pipeline-source-sub");

  if (!title || !sub) return;

  if (uploadTab === "drive") {
    if (selectedDriveFolder?.name) {
      title.textContent = `Google Drive: ${selectedDriveFolder.name}`;
      if (driveSyncState.status === "syncing") {
        sub.textContent = `Syncing ${formatNumber(driveSyncState.downloaded_count)} of ${formatNumber(driveSyncState.discovered_count || 0)} image(s) into backend staging`;
      } else if (isDriveSourceReady()) {
        sub.textContent = `Source ready · ${formatNumber(driveSyncState.downloaded_count || driveSyncState.discovered_count)} staged image(s)${selectedDriveFolder.id ? ` · ID ${selectedDriveFolder.id}` : ""}`;
      } else if (driveSyncState.status === "failed") {
        sub.textContent = driveSyncState.error || "The last Drive sync failed. Run Pipeline can retry backend staging, or you can sync again first.";
      } else {
        sub.textContent = `Selected Drive folder${selectedDriveFolder.id ? ` · ID ${selectedDriveFolder.id}` : ""} · Run Pipeline will fetch it on the backend if needed`;
      }
    } else {
      title.textContent = "Google Drive: no folder selected";
      if (driveConnected) {
        sub.textContent = "Select a folder on the Upload page before syncing or running the pipeline";
      } else if (googleAuthActive) {
        sub.textContent = "Confirm Google Drive to run from a backend-selected folder";
      } else {
        sub.textContent = "Connect Google Drive to run from a selected folder";
      }
    }
    return;
  }

  title.textContent = "Local staging";
  sub.textContent = "Current local-only pipeline flow remains available";
}

function renderDriveFolderSelection() {
  const selectEl = document.getElementById("drive-folder-select");
  const helperEl = document.getElementById("drive-folder-helper");
  const selectedNameEl = document.getElementById("drive-folder-selected-name");
  const selectedMetaEl = document.getElementById("drive-folder-selected-meta");
  const refreshBtn = document.getElementById("drive-folder-refresh-btn");

  setDriveFolderSelectOptions(selectEl, availableDriveFolders, selectedDriveFolder?.id || "");
  syncDriveSelectionControls();

  if (refreshBtn) {
    refreshBtn.disabled = !driveConnected || driveFoldersLoading || driveSyncState.status === "syncing";
  }

  if (helperEl) {
    if (!googleAuthActive) {
      helperEl.textContent = selectedDriveFolder?.name
        ? "A backend-selected folder is saved, but Google auth is inactive. Sign in again to load folders."
        : "Connect Google Drive to load available folders.";
    } else if (!driveConnected) {
      helperEl.textContent = selectedDriveFolder?.name
        ? "A backend-selected folder is saved. Confirm this Drive connection to use it."
        : "Confirm the Google Drive connection to load available folders.";
    } else if (driveSyncState.status === "syncing") {
      helperEl.textContent = `Syncing ${formatNumber(driveSyncState.downloaded_count)} of ${formatNumber(driveSyncState.discovered_count || 0)} image(s) from ${selectedDriveFolder?.name || "the selected folder"}...`;
    } else if (driveFoldersLoading) {
      helperEl.textContent = "Loading folders from Google Drive…";
    } else if (driveFolderError) {
      helperEl.textContent = driveFolderError;
    } else if (isDriveSourceReady()) {
      helperEl.textContent = `Source ready. ${formatNumber(driveSyncState.downloaded_count || driveSyncState.discovered_count)} image(s) are staged on the backend.`;
    } else if (selectedDriveFolder?.name) {
      helperEl.textContent = "This folder is saved in the backend. Sync is optional; Run Pipeline can fetch it on demand.";
    } else {
      helperEl.textContent = "Choose the Drive folder to sync or run directly from the backend.";
    }
  }

  if (selectedNameEl) {
    selectedNameEl.textContent = selectedDriveFolder?.name || "No folder selected";
  }

  if (selectedMetaEl) {
    if (!googleAuthActive) {
      selectedMetaEl.textContent = selectedDriveFolder?.id
        ? `Stored backend selection · Folder ID: ${selectedDriveFolder.id}`
        : "Manual upload mode still works without Drive.";
    } else if (!driveConnected) {
      selectedMetaEl.textContent = selectedDriveFolder?.id
        ? `Stored backend selection · Folder ID: ${selectedDriveFolder.id}`
        : "Confirm this Drive connection to enable folder staging.";
    } else if (driveSyncState.status === "syncing") {
      selectedMetaEl.textContent = `${formatNumber(driveSyncState.downloaded_count)} of ${formatNumber(driveSyncState.discovered_count || 0)} files downloading into ${driveSyncState.staging_dir || "data/staging"} · ${formatDriveSyncLimitLabel(driveSyncLimit)}`;
    } else if (isDriveSourceReady()) {
      selectedMetaEl.textContent = `${formatNumber(driveSyncState.downloaded_count || driveSyncState.discovered_count)} staged files · ${driveCameraLocation || "Using folder name for location"} · ${formatDriveSyncLimitLabel(driveSyncLimit)}`;
    } else if (selectedDriveFolder?.id) {
      selectedMetaEl.textContent = `${driveCameraLocation || "Using folder name for location"} · ${formatDriveSyncLimitLabel(driveSyncLimit)} · Folder ID: ${selectedDriveFolder.id}`;
    } else if (driveFolderError) {
      selectedMetaEl.textContent = "Folder selection is unavailable until the backend Drive auth flow is active.";
    } else {
      selectedMetaEl.textContent = "Select a folder in this panel, then run the pipeline from Drive mode.";
    }
  }

  syncDriveManualSelectionState();
  updatePipelineSourceSummary();
}

async function loadSelectedDriveFolderState({ silent = true } = {}) {
  if (!hasAppSession()) {
    return selectedDriveFolder;
  }

  try {
    const response = await getSelectedDriveFolder();
    selectedDriveFolder = response?.folder || null;
    applySelectedDriveFolderSettings(selectedDriveFolder);
    if (response?.sync) {
      driveSyncState = normalizeDriveSyncStatus(response.sync);
    }
    driveFolderError = "";
    return selectedDriveFolder;
  } catch (error) {
    driveFolderError = error.message || "Unable to load selected Drive folder";
    if (!silent) {
      showToast(driveFolderError, "warn");
    }
    return null;
  } finally {
    syncDriveUI();
    renderDriveFolderSelection();
  }
}

async function hydrateDriveFolderSelection({ silent = false } = {}) {
  if (!googleAuthActive || !driveConnected) {
    availableDriveFolders = [];
    driveFoldersLoading = false;
    driveFolderError = "";
    applyDriveSyncStatus(driveSyncState);
    renderDriveFolderSelection();
    return { folders: [], selectedFolder: selectedDriveFolder };
  }

  driveFoldersLoading = true;
  driveFolderError = "";
  renderDriveFolderSelection();

  try {
    const [foldersResult, selectedResult, syncResult] = await Promise.allSettled([
      getDriveFolders(),
      getSelectedDriveFolder(),
      getDriveSyncStatus()
    ]);

    if (foldersResult.status !== "fulfilled") {
      throw foldersResult.reason || new Error("Unable to load Drive folders");
    }

    const foldersResponse = foldersResult.value || {};
    const selectedResponse = selectedResult.status === "fulfilled"
      ? (selectedResult.value || {})
      : null;
    const syncResponse = syncResult.status === "fulfilled"
      ? syncResult.value
      : null;

    availableDriveFolders = normalizeDriveFolderOptions([
      ...(Array.isArray(foldersResponse?.folders) ? foldersResponse.folders : []),
      ...(selectedResponse?.folder ? [selectedResponse.folder] : []),
      ...(selectedDriveFolder?.id ? [selectedDriveFolder] : [])
    ]);

    if (selectedResponse) {
      selectedDriveFolder = selectedResponse.folder || null;
      applySelectedDriveFolderSettings(selectedDriveFolder);
    }

    if (syncResponse) {
      driveSyncState = normalizeDriveSyncStatus(syncResponse);
    } else if (selectedResponse?.sync) {
      driveSyncState = normalizeDriveSyncStatus(selectedResponse.sync);
    }

    return {
      folders: availableDriveFolders,
      selectedFolder: selectedDriveFolder
    };
  } catch (error) {
    driveFolderError = error.message || "Unable to load Drive folders";
    availableDriveFolders = normalizeDriveFolderOptions([
      ...availableDriveFolders,
      ...(selectedDriveFolder?.id ? [selectedDriveFolder] : [])
    ]);
    if (!silent) {
      showToast(driveFolderError, "warn");
    }
    return {
      folders: availableDriveFolders,
      selectedFolder: selectedDriveFolder
    };
  } finally {
    driveFoldersLoading = false;
    syncDriveUI();
    renderDriveFolderSelection();
  }
}

function handleDriveManualSelectionKeydown(event) {
  if (event?.key !== "Enter") {
    return;
  }

  event.preventDefault();
  void applyManualDriveFolderSelection();
}

async function applyManualDriveFolderSelection() {
  const inputEl = document.getElementById("drive-folder-manual-input");
  const rawValue = String(inputEl?.value || "").trim();

  if (!googleAuthActive) {
    setDriveManualSelectionFeedback("Sign in with Google before selecting a Drive folder.", "error");
    showToast("Sign in with Google first", "warn");
    return;
  }

  if (!driveConnected) {
    setDriveManualSelectionFeedback("Confirm the Google Drive connection before selecting a folder.", "error");
    showToast("Confirm the Google Drive connection first", "warn");
    return;
  }

  if (driveSyncState.status === "syncing") {
    setDriveManualSelectionFeedback("Wait for the current Drive sync to finish before changing folders.", "error");
    showToast("Wait for the current Drive sync to finish before changing folders", "warn");
    return;
  }

  if (!rawValue) {
    setDriveManualSelectionFeedback("Paste a Google Drive folder URL or raw folder ID first.", "error");
    syncDriveManualSelectionState();
    return;
  }

  driveManualSelectionPending = true;
  setDriveManualSelectionFeedback("Checking that Drive folder in the backend…", "muted");
  syncDriveManualSelectionState();

  try {
    const response = await saveSelectedDriveFolder(
      rawValue,
      null,
      driveCameraLocation || null,
      driveSyncLimit
    );
    const folder = response?.folder || null;

    if (!folder?.id || !folder?.name) {
      throw new Error("The backend did not return a valid Google Drive folder.");
    }

    selectedDriveFolder = folder;
    applySelectedDriveFolderSettings(selectedDriveFolder);
    availableDriveFolders = normalizeDriveFolderOptions([
      ...availableDriveFolders,
      folder
    ]);
    driveSyncState = normalizeDriveSyncStatus(response?.sync || null);
    driveFolderError = "";
    if (inputEl) {
      inputEl.value = "";
    }
    setDriveManualSelectionFeedback(`Selected Drive folder: ${folder.name}`, "success");
    syncDriveUI();
    renderDriveFolderSelection();
    showToast(`Selected Drive folder: ${folder.name}`, "success");
  } catch (error) {
    const message = error.message || "Unable to select that Google Drive folder";
    setDriveManualSelectionFeedback(message, "error");
    showToast(message, "warn");
  } finally {
    driveManualSelectionPending = false;
    syncDriveManualSelectionState();
  }
}

async function handleDriveFolderSelect(selectEl) {
  const folderId = selectEl?.value || "";

  if (driveSyncState.status === "syncing") {
    showToast("Wait for the current Drive sync to finish before changing folders", "warn");
    if (selectEl && selectedDriveFolder?.id) {
      selectEl.value = selectedDriveFolder.id;
    }
    return;
  }

  if (!folderId) {
    if (selectEl && selectedDriveFolder?.id) {
      selectEl.value = selectedDriveFolder.id;
    }
    renderDriveFolderSelection();
    return;
  }

  const folder = availableDriveFolders.find((item) => item.id === folderId);
  if (!folder) {
    showToast("Selected Drive folder was not found in the current list", "warn");
    renderDriveFolderSelection();
    return;
  }

  if (selectEl) selectEl.disabled = true;

  try {
    const response = await saveSelectedDriveFolder(
      folder.id,
      folder.name,
      driveCameraLocation || null,
      driveSyncLimit
    );
    selectedDriveFolder = response?.folder || folder;
    applySelectedDriveFolderSettings(selectedDriveFolder);
    driveSyncState = normalizeDriveSyncStatus(response?.sync || null);
    driveFolderError = "";
    setDriveManualSelectionFeedback(null);
    syncDriveUI();
    renderDriveFolderSelection();
    showToast(`Selected Drive folder: ${folder.name}`, "success");
  } catch (error) {
    driveFolderError = error.message || "Unable to save Drive folder selection";
    renderDriveFolderSelection();
    showToast(driveFolderError, "warn");
  } finally {
    if (selectEl) selectEl.disabled = false;
  }
}

async function handleDriveSyncSettingsChange() {
  const locationEl = document.getElementById("drive-camera-location-select");
  const limitEl = document.getElementById("drive-sync-limit-select");
  const nextLocation = String(locationEl?.value || "").trim();
  const nextLimit = normalizeDriveSyncLimitValue(limitEl?.value || "");

  if (driveSyncState.status === "syncing") {
    syncDriveSelectionControls();
    showToast("Wait for the current Drive sync to finish before changing sync settings", "warn");
    return;
  }

  driveCameraLocation = nextLocation;
  driveSyncLimit = nextLimit;

  if (!selectedDriveFolder?.id || !hasAppSession()) {
    syncDriveUI();
    renderDriveFolderSelection();
    return;
  }

  try {
    const response = await saveSelectedDriveFolder(
      selectedDriveFolder.id,
      selectedDriveFolder.name,
      driveCameraLocation || null,
      driveSyncLimit
    );
    selectedDriveFolder = response?.folder || {
      ...selectedDriveFolder,
      camera_location: driveCameraLocation || null,
      max_files: driveSyncLimit
    };
    applySelectedDriveFolderSettings(selectedDriveFolder);
    driveSyncState = normalizeDriveSyncStatus(response?.sync || null);
    driveFolderError = "";
    syncDriveUI();
    renderDriveFolderSelection();
  } catch (error) {
    driveFolderError = error.message || "Unable to save Drive sync settings";
    applySelectedDriveFolderSettings(selectedDriveFolder);
    syncDriveUI();
    renderDriveFolderSelection();
    showToast(driveFolderError, "warn");
  }
}

async function refreshDriveFolders() {
  if (!googleAuthActive) {
    showToast("Sign in with Google first", "warn");
    return;
  }

  if (!driveConnected) {
    showToast("Confirm the Google Drive connection first", "warn");
    return;
  }

  if (driveSyncState.status === "syncing") {
    showToast("Wait for the current Drive sync to finish before refreshing folders", "warn");
    return;
  }

  const result = await hydrateDriveFolderSelection();
  if (!driveFolderError) {
    setDriveManualSelectionFeedback(null);
    showToast(
      result.folders.length
        ? `Loaded ${result.folders.length} Drive folder${result.folders.length === 1 ? "" : "s"}`
        : "No Drive folders available",
      result.folders.length ? "success" : "warn"
    );
  }
}

async function triggerSync(buttonEl) {
  const helperEl = document.getElementById("drive-folder-helper");
  const selectedMetaEl = document.getElementById("drive-folder-selected-meta");
  const originalHtml = buttonEl?.innerHTML;

  if (!googleAuthActive) {
    showToast("Sign in with Google before syncing a Drive folder", "warn");
    return;
  }

  if (!driveConnected) {
    showToast("Confirm the Google Drive connection before syncing", "warn");
    return;
  }

  if (!selectedDriveFolder?.id) {
    showToast("Select a Google Drive folder before syncing", "warn");
    return;
  }

  if (driveSyncState.status === "syncing") {
    showToast("A Drive sync is already in progress", "warn");
    startDriveSyncPolling();
    return;
  }

  if (buttonEl) {
    buttonEl.disabled = true;
    buttonEl.textContent = "Syncing...";
  }

  driveFolderError = "";
  applyDriveSyncStatus({
    ...createEmptyDriveSyncState(),
    status: "syncing",
    source_ready: false,
    started_at: new Date().toISOString(),
    folder: {
      id: selectedDriveFolder.id,
      name: selectedDriveFolder.name
    },
    selected_folder: selectedDriveFolder,
    selected_folder_matches: true,
    staging_dir: driveSyncState.staging_dir || "data/staging",
    last_sync_message: `Syncing ${selectedDriveFolder.name} into backend staging`,
  });
  startDriveSyncPolling();

  if (helperEl) {
    helperEl.textContent = `Syncing ${selectedDriveFolder.name} into backend staging...`;
  }
  if (selectedMetaEl) {
    selectedMetaEl.textContent = `Preparing sync in ${driveSyncState.staging_dir || "data/staging"} · ${formatDriveSyncLimitLabel(driveSyncLimit)}`;
  }

  try {
    const syncRequest = syncSelectedDriveFolder(driveSyncLimit);
    window.setTimeout(() => {
      void loadDriveSyncStatus({ silent: true });
    }, 150);
    const response = await syncRequest;
    selectedDriveFolder = response?.folder || selectedDriveFolder;
    applySelectedDriveFolderSettings(selectedDriveFolder);
    const sync = normalizeDriveSyncStatus(response?.sync || null);
    applyDriveSyncStatus(sync);
    stopDriveSyncPolling();

    const stagedCount = Number(sync.downloaded_count || sync.discovered_count || 0);

    if (helperEl) {
      helperEl.textContent = `Synced ${formatNumber(stagedCount)} image${stagedCount === 1 ? "" : "s"} from Google Drive into backend staging.`;
    }

    if (selectedMetaEl && sync?.staging_dir) {
      selectedMetaEl.textContent = `Synced to ${sync.staging_dir} · ${formatDriveSyncLimitLabel(driveSyncLimit)} · Folder ID: ${selectedDriveFolder.id}`;
    }

    updatePipelineSourceSummary();
    showToast(
      response?.message || `Synced ${formatNumber(stagedCount)} image${stagedCount === 1 ? "" : "s"}`,
      "success"
    );
  } catch (error) {
    driveFolderError = error.message || "Unable to sync the selected Drive folder";
    await loadDriveSyncStatus({ silent: true });
    if (helperEl) {
      helperEl.textContent = driveFolderError;
    }
    showToast(driveFolderError, "warn");
  } finally {
    if (buttonEl) {
      buttonEl.disabled = false;
      buttonEl.innerHTML = originalHtml || "Sync Now";
    }
  }
}

// =========================
// SIDEBAR
// =========================
const collapseBtnListener = () => {
  const sidebar = document.getElementById("sidebar");
  const app = document.getElementById("main-app");
  const label = document.querySelector(".collapse-label");

  sidebarCollapsed = !sidebarCollapsed;

  if (sidebar) sidebar.classList.toggle("collapsed", sidebarCollapsed);
  if (app) app.classList.toggle("sidebar-collapsed", sidebarCollapsed);
  if (label) label.textContent = sidebarCollapsed ? "Expand" : "Collapse";
};

document.addEventListener("click", (e) => {
  const navItem = e.target.closest(".nav-item[data-page]");
  if (navItem) {
    showPage(navItem.dataset.page);
    return;
  }

  if (e.target.closest("#collapse-btn")) {
    collapseBtnListener();
  }
});

// =========================
// DASHBOARD
// =========================
function animateValue(el, start, end, duration, format) {
  const startTime = performance.now();

  function update(now) {
    const progress = Math.min((now - startTime) / duration, 1);
    const value = Math.floor(start + (end - start) * progress);

    if (format === "comma") {
      el.textContent = value.toLocaleString();
    } else {
      el.textContent = String(value);
    }

    if (progress < 1) {
      requestAnimationFrame(update);
    }
  }

  requestAnimationFrame(update);
}

function buildSpeciesDonut(data) {
  const svg = document.getElementById("species-svg");
  if (!svg) return;

  svg.querySelectorAll("circle[data-segment='true']").forEach((node) => node.remove());

  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  data.forEach((item) => {
    if (!item.value) return;
    const seg = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    const dash = (item.value / 100) * circumference;

    seg.setAttribute("cx", "65");
    seg.setAttribute("cy", "65");
    seg.setAttribute("r", String(radius));
    seg.setAttribute("fill", "none");
    seg.setAttribute("stroke", item.color);
    seg.setAttribute("stroke-width", "14");
    seg.setAttribute("stroke-dasharray", `${dash} ${circumference}`);
    seg.setAttribute("stroke-dashoffset", String(-offset + 82));
    seg.setAttribute("stroke-linecap", "round");
    seg.setAttribute("data-segment", "true");

    svg.appendChild(seg);
    offset += dash;
  });
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setHTML(id, value) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = value;
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

function formatPercent(value) {
  return `${Math.max(0, Math.round(Number(value || 0)))}%`;
}

function formatDecimal(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(2);
}

function getPercent(part, whole) {
  if (!whole) return 0;
  return (Number(part || 0) / Number(whole || 0)) * 100;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

function formatCameraName(fileName) {
  return (fileName || "Unknown").replace(/\.csv$/i, "");
}

function formatTimestampLabel(value) {
  if (!value) return "Unknown";
  try {
    return new Date(value).toLocaleString([], {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
  } catch (error) {
    return String(value);
  }
}

function formatDurationLabel(seconds) {
  if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) return "—";
  const total = Math.max(0, Math.round(Number(seconds)));
  const minutes = Math.floor(total / 60);
  const remainingSeconds = total % 60;
  return `${minutes} min ${String(remainingSeconds).padStart(2, "0")} s`;
}

function getSpeciesEmoji(species) {
  const value = (species || "").toLowerCase();
  if (value.includes("coyote")) return "🦊";
  if (value.includes("raccoon")) return "🦝";
  if (value.includes("bird")) return "🐦";
  if (value.includes("squirrel")) return "🐿️";
  if (value.includes("opossum")) return "🦡";
  if (value.includes("human")) return "🚶";
  if (value.includes("blank")) return "🖼️";
  return "🐾";
}

function setDashboardStat(id, nextValue, format = "comma") {
  const el = document.getElementById(id);
  if (!el) return;
  const previousText = (el.textContent || "0").replaceAll(",", "");
  const previousValue = Number(previousText || 0);
  animateValue(el, Number.isFinite(previousValue) ? previousValue : 0, Number(nextValue || 0), 500, format);
}

function setPipelineStep(stepEl, pct, countText) {
  if (!stepEl) return;
  const normalized = Math.max(0, Math.min(100, Math.round(pct || 0)));
  stepEl.classList.remove("done", "active", "idle");
  stepEl.classList.add(normalized >= 100 ? "done" : normalized > 0 ? "active" : "idle");

  const pctEl = stepEl.querySelector(".pipeline-pct");
  const countEl = stepEl.querySelector(".pipeline-count");
  const fillEl = stepEl.querySelector(".prog-fill");

  if (pctEl) pctEl.textContent = formatPercent(normalized);
  if (countEl) countEl.textContent = countText;
  if (fillEl) {
    fillEl.dataset.width = `${normalized}%`;
    fillEl.style.width = `${normalized}%`;
  }
}

function renderDashboardCameraChips(files = []) {
  const container = document.getElementById("dashboard-camera-chip-list");
  if (!container) return;

  if (!files.length) {
    container.innerHTML = `<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 9px;background:#F7FAFC;border:1.5px solid var(--border);border-radius:20px;font-size:11.5px;font-weight:500;color:var(--muted)">No export artifacts yet</span>`;
    return;
  }

  container.innerHTML = files.map((file) => `
    <span style="display:inline-flex;align-items:center;gap:5px;padding:3px 9px;background:#F0FFF4;border:1.5px solid #9AE6B4;border-radius:20px;font-size:11.5px;font-weight:600;color:#276749">
      <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
      ${escapeHtml(formatCameraName(file.name))}
    </span>
  `).join("");
}

function renderDashboardCameraStatus(files = []) {
  const container = document.getElementById("dashboard-camera-status-list");
  if (!container) return;

  if (!files.length) {
    container.innerHTML = `
      <div class="camera-card" style="border-left:3px solid #CBD5E0">
        <div class="camera-name">No output files generated yet</div>
        <div class="camera-stat"><span class="camera-stat-label">Images</span><span class="camera-stat-val">0</span></div>
        <div class="camera-stat"><span class="camera-stat-label">Status</span><span class="camera-stat-val">Waiting for pipeline output</span></div>
      </div>
    `;
    return;
  }

  container.innerHTML = files.map((file) => `
    <div class="camera-card" style="border-left:3px solid #48BB78">
      <div class="camera-name" style="display:flex;align-items:center;gap:6px">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#48BB78" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
        ${escapeHtml(formatCameraName(file.name))}
      </div>
      <div class="camera-stat"><span class="camera-stat-label">Rows</span><span class="camera-stat-val">${formatNumber(file.rows)}</span></div>
      <div class="camera-stat"><span class="camera-stat-label">Source</span><span class="camera-stat-val">${escapeHtml(file.path || file.name)}</span></div>
      <span class="camera-sync sync-ok">✓ Ready</span>
    </div>
  `).join("");
}

function renderDashboardActivity(summary, validation, exportSummary) {
  const container = document.getElementById("dashboard-activity-list");
  if (!container) return;

  const items = [
    {
      badge: "Pipeline complete",
      badgeClass: "badge-blue",
      text: `${formatNumber(summary?.processed_images || 0)} images processed`,
      time: summary?.last_run?.date || "Unknown date"
    },
    {
      badge: "Review queue",
      badgeClass: "badge-yellow",
      text: `${formatNumber(summary?.pending_review || 0)} items need manual review`,
      time: "Current artifacts"
    },
    {
      badge: "Validation",
      badgeClass: "badge-yellow",
      text: `${formatNumber(validation?.outside_range || 0)} outside range, ${formatNumber(validation?.unprocessed || 0)} unprocessed`,
      time: "Current artifacts"
    },
    {
      badge: "Export files",
      badgeClass: "badge-green",
      text: exportSummary?.file_count
        ? `${formatNumber(exportSummary.file_count)} export file(s) ready`
        : "No export artifacts generated",
      time: exportSummary?.output_dir || "data/outputs/by_location"
    }
  ];

  container.innerHTML = items.map((item) => `
    <div class="activity-item">
      <span class="activity-badge ${item.badgeClass}">${escapeHtml(item.badge)}</span>
      <span class="activity-text">${escapeHtml(item.text)}</span>
      <span class="activity-time">${escapeHtml(item.time)}</span>
    </div>
  `).join("");
}

function applyDashboardSummary(summary, validation = validationData, exportSummary = exportData) {
  dashboardSummary = summary;

  const total = Number(summary?.total_images || 0);
  const processed = Number(summary?.processed_images || 0);
  const animals = Number(summary?.animals_detected || 0);
  const pendingReview = Number(summary?.pending_review || 0);
  const warnings = Number(summary?.warnings || 0);
  const runSuccess = Number(summary?.last_run?.success_rate || 0);
  const runFailure = Math.max(100 - runSuccess, 0);
  const validationWarnings = Number(validation?.outside_range || 0) + Number(validation?.column_issue_count || 0);
  const validRecords = Math.max((exportSummary?.total_rows ?? processed) - Number(validation?.outside_range || 0), 0);
  const uploadPct = total > 0 ? 100 : 0;
  const classifyPct = getPercent(processed, total);
  const reviewPct = getPercent(Math.max(processed - pendingReview, 0), processed || total);
  const validatePct = getPercent(validRecords, processed || total);
  const exportPct = exportSummary?.file_count ? 100 : 0;
  const throughput = "Not available";
  const animalShare = getPercent(animals, processed || total);
  const otherShare = Math.max(100 - animalShare, 0);
  const exportFiles = exportSummary?.files || [];

  setDashboardStat("stat-total-images", total);
  setDashboardStat("stat-processed-images", processed);
  setDashboardStat("stat-animals-detected", animals);
  setDashboardStat("stat-pending-review", pendingReview);
  setDashboardStat("stat-warnings", warnings);

  setText("stat-processed-sub", total ? `${formatPercent(getPercent(processed, total))} complete` : "No processed images yet");
  setText("stat-animals-sub", animals ? "Detected in generated output files" : "No animal detections in current artifacts");
  setText("stat-review-sub", pendingReview ? "Needs manual attention" : "No current review queue");
  setText("stat-warnings-sub", warnings ? "Derived from validation output" : "No validation warnings");

  setText("run-pct", formatPercent(runSuccess));
  document.getElementById("run-circle")?.setAttribute("stroke-dasharray", `${(Math.max(0, Math.min(100, runSuccess)) / 100) * 327} 327`);
  setText("run-success-count", formatNumber(processed));
  setText("run-success-rate", formatPercent(runSuccess));
  setText("run-failure-count", formatNumber(Math.max(total - processed, 0)));
  setText("run-failure-rate", formatPercent(runFailure));
  setText("run-start-time", summary?.last_run?.date || "Unknown");
  setText("run-duration", summary?.last_run?.duration || "Unknown");
  setText("run-throughput", throughput);

  renderDashboardCameraChips(exportFiles);
  setText(
    "dashboard-review-shortcut-title",
    pendingReview ? `${formatNumber(pendingReview)} images ready for review` : "No review items currently queued"
  );
  setText(
    "dashboard-review-shortcut-sub",
    pendingReview ? "Generated from speciesnet_review.csv" : "Current pipeline artifacts do not require review"
  );

  setText("species-total", formatNumber(animals));
  setText("species-total-label", animals ? "Animal rows" : "No animals");
  const speciesLegend = document.getElementById("species-legend-list");
  if (speciesLegend) {
    speciesLegend.innerHTML = `
      <div class="legend-item">
        <div class="legend-dot" style="background:#DD6B20"></div>
        <span class="legend-name">Animal detections</span>
        <span class="legend-count">${formatNumber(animals)}</span>
        <span class="legend-pct" style="color:#DD6B20">${formatPercent(animalShare)}</span>
      </div>
      <div class="legend-item">
        <div class="legend-dot" style="background:#CBD5E0"></div>
        <span class="legend-name">Other / blank</span>
        <span class="legend-count">${formatNumber(Math.max(processed - animals, 0))}</span>
        <span class="legend-pct" style="color:#718096">${formatPercent(otherShare)}</span>
      </div>
    `;
  }
  buildSpeciesDonut([
    { value: animalShare, color: "#DD6B20" },
    { value: otherShare, color: "#CBD5E0" }
  ]);

  setText("dashboard-human-title", pendingReview ? `${formatNumber(pendingReview)} rows pending manual review` : "No pending manual review");
  setHTML(
    "dashboard-human-sub",
    pendingReview
      ? "These rows come from <strong>speciesnet_review.csv</strong> and should be reviewed before export."
      : "Current output files do not include pending manual review rows."
  );

  renderDashboardCameraStatus(exportFiles);
  renderDashboardActivity(summary, validation, exportSummary);

  const steps = document.querySelectorAll(".pipeline-step");
  setPipelineStep(steps[0], uploadPct, `${formatNumber(total)} images`);
  setPipelineStep(steps[1], classifyPct, total ? `${formatNumber(processed)} / ${formatNumber(total)}` : "No images");
  setPipelineStep(steps[2], reviewPct, pendingReview ? `${formatNumber(pendingReview)} pending` : "Nothing pending");
  setPipelineStep(steps[3], validatePct, validation ? `${formatNumber(validationWarnings)} warnings` : "Not validated");
  setPipelineStep(steps[4], exportPct, exportSummary?.file_count ? `${formatNumber(exportSummary.total_rows)} rows ready` : "No export files");

  const flowFill = document.getElementById("pipeline-flow-fill");
  if (flowFill) {
    flowFill.style.width = `${Math.max(uploadPct, classifyPct, reviewPct, validatePct, exportPct)}%`;
  }
}

async function loadDashboardData() {
  try {
    const [summary, exportSummary] = await Promise.all([
      getDashboardSummary(),
      startExportRequest().catch(() => null)
    ]);
    dashboardSummary = summary;
    if (exportSummary) exportData = exportSummary;
    applyDashboardSummary(summary, validationData, exportData);
    pageLoadState.dashboard = true;
  } catch (error) {
    applyDashboardSummary(null, validationData, exportData);
    showToast(error.message || "Unable to load dashboard summary", "warn");
  }
}

function getPipelineMetrics(status) {
  const result = status?.result || {};
  const steps = result?.steps || {};
  const manifestRows = Number(steps?.manifest?.rows_written || 0);
  const processedRows = Number(
    steps?.metadata_merged?.rows_written
    || steps?.metadata_exif?.rows_written
    || 0
  );
  const reviewItems = Number(steps?.postprocess?.review_items || 0);
  const exportedRows = Number(steps?.output?.rows_written || 0);
  const failureCount = status?.status === "completed"
    ? Math.max(manifestRows - processedRows, 0)
    : null;
  const throughput = result?.elapsed_seconds && processedRows
    ? processedRows / Number(result.elapsed_seconds)
    : null;

  return {
    manifestRows,
    processedRows,
    remainingRows: status?.status === "completed" ? Math.max(manifestRows - processedRows, 0) : null,
    reviewItems,
    exportedRows,
    failureCount,
    throughput
  };
}

function getPipelineSourceMode(status) {
  return String(
    status?.result?.source?.mode ||
    status?.payload?.source_mode ||
    (uploadTab === "drive" ? "drive" : "local")
  ).toLowerCase();
}

function getPipelineOverallStatusLabel(status) {
  const state = String(status?.status || "idle").toLowerCase();
  const currentStep = String(status?.progress?.step || status?.current_step || "").toLowerCase();

  if (!status?.run_id) return "Idle";
  if (state === "running" && currentStep === "queued") return "Queued";
  if (state === "running") return "Running";
  if (state === "completed") return "Completed";
  if (state === "failed") return "Failed";
  return "Idle";
}

function getPipelineCurrentStepLabel(status) {
  return status?.progress?.step || status?.current_step || (status?.run_id ? "Waiting for backend updates" : "Waiting for a run");
}

function getPipelinePanelSnapshot(status) {
  const sourceMode = getPipelineSourceMode(status);
  const state = String(status?.status || "idle").toLowerCase();
  const currentStepKey = String(status?.progress?.step || status?.current_step || "").toLowerCase();
  const progressDetails = status?.progress?.details || {};
  const completedImageCount = Number(status?.result?.source?.image_count || 0);
  const discoveredCount = Number(driveSyncState.discovered_count || 0);
  const downloadedCount = Number(driveSyncState.downloaded_count || 0);
  const rawProcessedImages = Number(progressDetails?.processed_images);
  const rawTotalImages = Number(progressDetails?.total_images);
  const mlActive = state === "running" && currentStepKey.includes("run speciesnet");
  const totalImages = mlActive && Number.isFinite(rawTotalImages) && rawTotalImages >= 0
    ? rawTotalImages
    : null;
  const processedImages = mlActive
    ? (Number.isFinite(rawProcessedImages) && rawProcessedImages >= 0 ? rawProcessedImages : 0)
    : null;
  const mlProgressPercent = mlActive && totalImages && totalImages > 0
    ? Math.max(0, Math.min(100, Math.round((processedImages / totalImages) * 100)))
    : 0;

  let discovered = null;
  let downloaded = null;

  if (sourceMode === "drive") {
    discovered = discoveredCount || (completedImageCount > 0 ? completedImageCount : null);
    downloaded = downloadedCount || (status?.status === "completed" && completedImageCount > 0 ? completedImageCount : null);
  } else if (status?.status === "completed" && completedImageCount > 0) {
    discovered = completedImageCount;
  }

  return {
    overallStatus: getPipelineOverallStatusLabel(status),
    currentStep: getPipelineCurrentStepLabel(status),
    discovered,
    downloaded,
    currentFile: sourceMode === "drive" ? (driveSyncState.current_file || null) : null,
    logPath: status?.log_path || null,
    error: status?.error || (sourceMode === "drive" ? driveSyncState.error : null) || null,
    mlActive: mlActive && totalImages !== null,
    processedImages,
    totalImages,
    mlProgressPercent
  };
}

function setPipelineDetailValue(element, value, fallback = "—") {
  if (!element) return;

  const hasValue = !(
    value === null ||
    value === undefined ||
    (typeof value === "string" && value.trim() === "")
  );
  const text = hasValue ? String(value) : fallback;
  element.textContent = text;
  element.title = hasValue ? text : "";
}

function buildRunHistoryRows(status) {
  if (!status?.run_id) {
    return `
      <tr>
        <td colspan="7" style="color:var(--muted);padding:18px 12px">
          No real backend run history is available yet. Start a pipeline run from this page to populate the latest run state.
        </td>
      </tr>
    `;
  }

  const metrics = getPipelineMetrics(status);
  const batchLabel = status?.payload?.batch_size === "all"
    ? "All"
    : (status?.payload?.batch_size || "Unknown");
  const statusClass = status?.status === "completed"
    ? "pill-green"
    : status?.status === "failed"
      ? "pill-red"
      : "pill-yellow";
  const statusLabel = status?.status === "completed"
    ? "Success"
    : status?.status === "failed"
      ? "Failed"
      : status?.status === "running"
        ? "Running"
        : "Idle";
  const failureText = metrics.failureCount === null ? "—" : formatNumber(metrics.failureCount);
  const durationText = status?.status === "running"
    ? "In progress"
    : (status?.result?.elapsed_seconds ? formatDurationLabel(status.result.elapsed_seconds) : "—");
  const imageCountText = metrics.manifestRows
    ? formatNumber(metrics.manifestRows)
    : (batchLabel === "All" ? "All staged" : batchLabel);
  const detailId = String(status.run_id).replace(/[^a-zA-Z0-9_-]/g, "");
  const notes = Array.isArray(status?.result?.notes) ? status.result.notes : [];
  const detailContent = status?.status === "running"
    ? `
      <div class="rh-detail-inner">
        <div class="rh-detail-section">
          <div class="rh-detail-label">Backend Status</div>
          <div class="rh-detail-stat">Running <span>See the status panel above for live SpeciesNet counts</span></div>
          <div class="rh-detail-stat">${escapeHtml(formatTimestampLabel(status.started_at))} <span>started</span></div>
        </div>
      </div>
    `
    : `
      <div class="rh-detail-inner">
        <div class="rh-detail-section">
          <div class="rh-detail-label">Results</div>
          <div class="rh-detail-stat">${formatNumber(metrics.processedRows)} <span>processed</span></div>
          <div class="rh-detail-stat">${formatNumber(metrics.reviewItems)} <span>queued for review</span></div>
          <div class="rh-detail-stat">${formatNumber(metrics.exportedRows)} <span>rows written to export files</span></div>
        </div>
        <div class="rh-detail-section">
          <div class="rh-detail-label">Performance</div>
          <div class="rh-detail-stat">${formatDecimal(metrics.throughput)} <span>img / sec</span></div>
          <div class="rh-detail-stat">${escapeHtml(formatTimestampLabel(status.started_at))} → ${escapeHtml(formatTimestampLabel(status.finished_at || status.started_at))} <span>time range</span></div>
        </div>
        <div class="rh-detail-section">
          <div class="rh-detail-label">Notes</div>
          ${notes.length
            ? notes.map((note) => `<div class="rh-detail-stat">${escapeHtml(note)}</div>`).join("")
            : `<div class="rh-detail-stat">No backend notes recorded</div>`}
        </div>
      </div>
    `;

  return `
    <tr>
      <td><span class="batch-num">${escapeHtml(String(status.run_id))}</span></td>
      <td>${escapeHtml(formatTimestampLabel(status.finished_at || status.started_at))}</td>
      <td>${escapeHtml(String(imageCountText))}</td>
      <td>${escapeHtml(durationText)}</td>
      <td><span class="status-pill ${statusClass}">${escapeHtml(statusLabel)}</span></td>
      <td><span class="${metrics.failureCount ? "failure-warn" : "failure-zero"}">${escapeHtml(String(failureText))}</span></td>
      <td><button class="rh-expand-btn" id="rh-btn-${detailId}" onclick="toggleRunDetail('${detailId}')">
        Details
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
      </button></td>
    </tr>
    <tr class="rh-detail-row" id="rh-detail-${detailId}">
      <td colspan="7">
        ${detailContent}
      </td>
    </tr>
  `;
}

function getRunSurfaceConfigs() {
  return [
    {
      kind: "main",
      buttonId: "run-btn",
      labelId: "run-btn-label",
      noteId: "run-ready-note",
      panelId: "run-progress",
      progressLabelId: "run-progress-label-text",
      fillId: "run-fill",
      etaId: "run-eta",
      statusId: "rs-status",
      stepId: "rs-step",
      discoveredId: "rs-discovered",
      downloadedId: "rs-downloaded",
      mlProgressId: "run-ml-progress",
      mlProgressSummaryId: "run-ml-progress-summary",
      mlProgressFillId: "run-ml-progress-fill",
      mlProcessedId: "run-ml-processed",
      mlTotalId: "run-ml-total",
      currentFileId: "run-current-file",
      logPathId: "run-log-path",
      errorId: "run-error-state"
    },
    {
      kind: "drive",
      buttonId: "drive-run-btn",
      labelId: "drive-run-btn-label",
      noteId: "drive-run-note",
      panelId: "drive-run-progress",
      progressLabelId: "drive-run-progress-label-text",
      fillId: "drive-run-fill",
      etaId: "drive-run-eta",
      statusId: "drive-rs-status",
      stepId: "drive-rs-step",
      discoveredId: "drive-rs-discovered",
      downloadedId: "drive-rs-downloaded",
      mlProgressId: "drive-run-ml-progress",
      mlProgressSummaryId: "drive-run-ml-progress-summary",
      mlProgressFillId: "drive-run-ml-progress-fill",
      mlProcessedId: "drive-run-ml-processed",
      mlTotalId: "drive-run-ml-total",
      currentFileId: "drive-run-current-file",
      logPathId: "drive-run-log-path",
      errorId: "drive-run-error-state"
    }
  ];
}

function applyPipelineStatusToSurface(surface, status) {
  const btn = document.getElementById(surface.buttonId);
  const label = document.getElementById(surface.labelId);
  const note = document.getElementById(surface.noteId);
  const panel = document.getElementById(surface.panelId);
  const progressLabel = document.getElementById(surface.progressLabelId);
  const fill = document.getElementById(surface.fillId);
  const eta = document.getElementById(surface.etaId);
  const statusValue = document.getElementById(surface.statusId);
  const stepValue = document.getElementById(surface.stepId);
  const discoveredValue = document.getElementById(surface.discoveredId);
  const downloadedValue = document.getElementById(surface.downloadedId);
  const mlProgressWrap = document.getElementById(surface.mlProgressId);
  const mlProgressSummary = document.getElementById(surface.mlProgressSummaryId);
  const mlProgressFill = document.getElementById(surface.mlProgressFillId);
  const mlProcessedValue = document.getElementById(surface.mlProcessedId);
  const mlTotalValue = document.getElementById(surface.mlTotalId);
  const currentFileValue = document.getElementById(surface.currentFileId);
  const logPathValue = document.getElementById(surface.logPathId);
  const errorValue = document.getElementById(surface.errorId);
  const state = status?.status || "idle";
  const hasLatestRun = Boolean(status?.run_id);
  const currentStep = status?.progress?.step || status?.current_step || "";
  const latestLogLine = status?.progress?.message || status?.latest_log_line || "";
  const snapshot = getPipelinePanelSnapshot(status);

  if (btn) {
    btn.classList.remove("idle", "running");
    btn.classList.add(state === "running" ? "running" : "idle");
    if (surface.kind === "drive") {
      btn.disabled = state === "running" || !canRunDrivePipeline();
    } else if (uploadTab === "drive") {
      btn.disabled = state === "running" || !canRunDrivePipeline();
    } else {
      btn.disabled = false;
    }
  }

  if (label) {
    label.textContent = state === "running"
      ? "Pipeline Running"
      : "Run Pipeline";
  }

  if (note) {
    if (state === "running") {
      note.textContent = currentStep
        ? `Run ${status.run_id} is running: ${currentStep}.`
        : `Run ${status.run_id} started ${formatTimestampLabel(status.started_at)}.`;
    } else if (state === "completed") {
      note.textContent = `Last run ${status.run_id} completed ${formatTimestampLabel(status.finished_at)}.`;
    } else if (state === "failed") {
      note.textContent = status.error
        ? `Last run ${status.run_id} failed: ${status.error}`
        : `Last run ${status.run_id} failed.`;
    } else if (surface.kind === "drive") {
      note.textContent = getDriveRunIdleNote();
    } else if (uploadTab === "drive") {
      note.textContent = getDriveRunIdleNote();
    } else {
      note.textContent = hasLatestRun
        ? `Latest backend state: ${state}`
        : "Ready to start a backend pipeline run";
    }
  }

  if (panel) {
    panel.style.display = "block";
  }

  if (progressLabel) {
    progressLabel.textContent = state === "running"
      ? currentStep || "Pipeline running in backend"
      : state === "completed"
        ? "Latest run completed"
        : state === "failed"
          ? "Latest run failed"
          : "No active pipeline run";
  }

  if (eta) {
    eta.textContent = state === "running"
      ? latestLogLine || "Backend log is updating"
      : state === "completed"
        ? `Completed ${formatTimestampLabel(status.finished_at)}`
        : state === "failed"
          ? (status.error || "See backend log for details")
          : surface.kind === "drive"
            ? "Run becomes available once a Drive folder is selected"
            : "No active run";
  }

  if (fill) {
    fill.style.width = state === "completed"
      ? "100%"
      : state === "failed"
        ? "100%"
        : state === "running"
          ? `${getDriveSyncStepPercent()}%`
          : "0%";
  }

  if (statusValue) {
    statusValue.textContent = snapshot.overallStatus;
    statusValue.style.color = state === "failed"
      ? "#E53E3E"
      : state === "completed"
        ? "#38A169"
        : state === "running"
          ? "var(--blue)"
          : "var(--text)";
  }
  if (stepValue) {
    setPipelineDetailValue(stepValue, snapshot.currentStep, "Waiting for a run");
  }
  if (discoveredValue) {
    discoveredValue.textContent = snapshot.discovered === null ? "—" : formatNumber(snapshot.discovered);
  }
  if (downloadedValue) {
    downloadedValue.textContent = snapshot.downloaded === null ? "—" : formatNumber(snapshot.downloaded);
  }
  if (mlProgressWrap) {
    mlProgressWrap.style.display = snapshot.mlActive ? "block" : "none";
  }
  if (mlProgressSummary) {
    mlProgressSummary.textContent = snapshot.mlActive
      ? `${formatNumber(snapshot.processedImages || 0)} / ${formatNumber(snapshot.totalImages || 0)} images`
      : "—";
  }
  if (mlProgressFill) {
    mlProgressFill.style.width = snapshot.mlActive ? `${snapshot.mlProgressPercent}%` : "0%";
  }
  if (mlProcessedValue) {
    mlProcessedValue.textContent = snapshot.mlActive ? formatNumber(snapshot.processedImages || 0) : "—";
  }
  if (mlTotalValue) {
    mlTotalValue.textContent = snapshot.mlActive ? formatNumber(snapshot.totalImages || 0) : "—";
  }
  if (currentFileValue) {
    setPipelineDetailValue(currentFileValue, snapshot.currentFile);
  }
  if (logPathValue) {
    setPipelineDetailValue(logPathValue, snapshot.logPath);
  }
  if (errorValue) {
    setPipelineDetailValue(errorValue, snapshot.error);
    errorValue.style.color = snapshot.error ? "#742A2A" : "var(--muted)";
    if (errorValue.parentElement) {
      errorValue.parentElement.style.background = snapshot.error ? "#FFF5F5" : "#F7FAFC";
      errorValue.parentElement.style.borderColor = snapshot.error ? "#FEB2B2" : "var(--border)";
    }
  }
}

function applyPipelineStatus(status) {
  pipelineStatus = status;
  const historyBody = document.getElementById("run-history-body");
  const historyNote = document.getElementById("run-history-note");

  const state = status?.status || "idle";
  runningModel = state === "running";
  const hasLatestRun = Boolean(status?.run_id);

  getRunSurfaceConfigs().forEach((surface) => {
    applyPipelineStatusToSurface(surface, status);
  });

  if (historyBody) {
    historyBody.innerHTML = buildRunHistoryRows(status);
  }
  if (historyNote) {
    historyNote.textContent = hasLatestRun ? "Latest backend run" : "No real run history yet";
  }

  syncDriveUI();
}

async function loadPipelineStatus({ silent = false } = {}) {
  try {
    const status = await getPipelineStatus();
    applyPipelineStatus(status);

    if (status?.status === "running") {
      startPipelineStatusPolling();
    } else {
      stopPipelineStatusPolling();
    }

    return status;
  } catch (error) {
    if (!silent) {
      showToast(error.message || "Unable to load pipeline status", "warn");
    }
    applyPipelineStatus(null);
    stopPipelineStatusPolling();
    return null;
  }
}

function startPipelineStatusPolling() {
  if (pipelineStatusPollId) return;
  pipelineStatusPollId = window.setInterval(() => {
    void loadPipelineStatus({ silent: true });
    if (runningModel && getPipelineSourceMode(pipelineStatus) === "drive" && !driveSyncPollId) {
      void loadDriveSyncStatus({ silent: true });
    }
  }, 3000);
}

function stopPipelineStatusPolling() {
  if (!pipelineStatusPollId) return;
  window.clearInterval(pipelineStatusPollId);
  pipelineStatusPollId = null;
}

// =========================
// UPLOAD
// =========================
function switchUploadTab(tab) {
  uploadTab = tab;

  const manual = document.getElementById("upload-manual");
  const drive = document.getElementById("upload-drive");
  const tabManual = document.getElementById("tab-manual");
  const tabDrive = document.getElementById("tab-drive");

  if (manual) manual.style.display = tab === "manual" ? "block" : "none";
  if (drive) drive.style.display = tab === "drive" ? "block" : "none";

  if (tabManual) tabManual.classList.toggle("active", tab === "manual");
  if (tabDrive) tabDrive.classList.toggle("active", tab === "drive");

  updatePipelineSourceSummary();

  if (tab === "drive" && driveConnected) {
    void hydrateDriveFolderSelection({ silent: true });
    void loadDriveSyncStatus({ silent: true });
  }
}

function togglePause(btn) {
  uploadPaused = !uploadPaused;

  const fill = document.getElementById("upload-prog-fill");
  const pct = document.getElementById("upload-prog-pct");
  const pill = document.getElementById("upload-status-pill");
  const label = document.getElementById("pause-label");

  if (uploadPaused) {
    if (pill) pill.textContent = "Paused";
    if (label) label.textContent = "Resume";
    showToast("Upload paused", "warn");
  } else {
    if (pill) pill.textContent = "Uploading…";
    if (label) label.textContent = "Pause";
    if (fill) fill.style.width = "68%";
    if (pct) pct.textContent = "68%";
    showToast("Upload resumed", "success");
  }

  btn.dataset.paused = uploadPaused ? "true" : "false";
}

function selectLocCard(card) {
  document.querySelectorAll(".loc-select-card").forEach((el) => el.classList.remove("selected"));
  card.classList.add("selected");
}

// =========================
// MODEL
// =========================
function updateSlider(slider) {
  const value = Number(slider.value);
  const output = document.getElementById("threshold-val");
  if (output) output.textContent = `${value}%`;
}

async function toggleRunModel(sourceModeOverride = null) {
  const btn = document.getElementById("run-btn");
  const note = document.getElementById("run-ready-note");
  const driveBtn = document.getElementById("drive-run-btn");
  const driveNote = document.getElementById("drive-run-note");
  const sourceMode = sourceModeOverride || (uploadTab === "drive" ? "drive" : "local");

  if (runningModel) {
    showToast("Pipeline stop is not wired yet. Check the backend status or log file for progress.", "warn");
    return;
  }

  const threshold = Number(document.getElementById("threshold-slider")?.value || 80);
  const batchSize = document.getElementById("batch-select")?.value || "1000";

  if (sourceMode === "drive") {
    await loadSelectedDriveFolderState({ silent: true });
    await loadDriveSyncStatus({ silent: true });
    if (!driveConnected) {
      if (note) {
        note.textContent = googleAuthActive
          ? "Confirm the Google Drive connection before running the pipeline in Drive mode."
          : "Sign in with Google before running the pipeline in Drive mode.";
      }
      if (driveNote) {
        driveNote.textContent = googleAuthActive
          ? "Confirm the Google Drive connection before running the pipeline in Drive mode."
          : "Sign in with Google before running the pipeline in Drive mode.";
      }
      showToast(
        googleAuthActive
          ? "Confirm the Google Drive connection before running the pipeline from Drive mode"
          : "Sign in with Google before running the pipeline from Drive mode",
        "warn"
      );
      return;
    }
    if (!selectedDriveFolder?.id) {
      if (note) {
        note.textContent = driveFolderError || "Select a Google Drive folder on the Upload page before running the pipeline.";
      }
      if (driveNote) {
        driveNote.textContent = driveFolderError || "Select a Google Drive folder before running the pipeline.";
      }
      showToast("Select a Google Drive folder before running the pipeline from Drive mode", "warn");
      return;
    }

    if (driveSyncState.status === "syncing") {
      const message = "Drive sync is still in progress. Wait for it to finish before starting the pipeline.";
      if (note) note.textContent = message;
      if (driveNote) driveNote.textContent = message;
      showToast(message, "warn");
      return;
    }
  }

  if (btn) btn.disabled = true;
  if (driveBtn) driveBtn.disabled = true;
  if (note) {
    note.textContent = sourceMode === "drive" && selectedDriveFolder?.name
      ? `Submitting backend run for Drive folder ${selectedDriveFolder.name}...`
      : "Submitting run to backend...";
  }
  if (driveNote) {
    driveNote.textContent = sourceMode === "drive" && selectedDriveFolder?.name
      ? `Submitting backend run for Drive folder ${selectedDriveFolder.name}...`
      : "Submitting run to backend...";
  }

  try {
    const response = await runPipeline({
      source_mode: sourceMode,
      confidence_threshold: threshold,
      batch_size: batchSize,
      remove_burst_duplicates: true,
      exclude_humans: true
    });

    runningModel = true;
    if (note) note.textContent = response.message || "Pipeline submitted to backend";
    if (driveNote) {
      driveNote.textContent = sourceMode === "drive"
        ? "Pipeline submitted. The backend will reuse the staged cache or fetch the selected Drive folder automatically."
        : (response.message || "Pipeline submitted to backend");
    }
    if (sourceMode === "drive") {
      window.setTimeout(() => {
        void loadDriveSyncStatus({ silent: true });
      }, 150);
    }
    await loadPipelineStatus({ silent: true });
    showToast(response.message || "Model run started", "success");
  } catch (error) {
    if (note) note.textContent = error.message || "Unable to start pipeline";
    if (driveNote) driveNote.textContent = error.message || "Unable to start pipeline";
    showToast(error.message || "Unable to start pipeline", "warn");
  } finally {
    applyPipelineStatus(pipelineStatus);
  }
}

function toggleDriveRunModel() {
  return toggleRunModel("drive");
}

function toggleRunDetail(id) {
  const row = document.getElementById(`rh-detail-${id}`);
  const btn = document.getElementById(`rh-btn-${id}`);

  if (!row) return;

  const open = row.classList.contains("open");
  row.classList.toggle("open", !open);

  if (btn) {
    btn.classList.toggle("open", !open);
  }
}

// =========================
// REVIEW
// =========================
function getFilteredReviewItems() {
  let items = [...reviewItems];

  if (reviewFilter !== "all") {
    items = items.filter((item) => item.status === reviewFilter);
  }

  if (humanFilterOnly) {
    items = items.filter((item) => item.humanDetected);
  }

  if (sortMode === "low-confidence") {
    items.sort((a, b) => a.confidence - b.confidence);
  }

  return items;
}

function renderReviewQueue() {
  const container = document.getElementById("review-queue-list");
  const count = document.getElementById("queue-count");
  const completeBanner = document.getElementById("review-complete-banner");
  if (!container) return;

  const items = getFilteredReviewItems();
  container.innerHTML = "";

  if (count) count.textContent = `${items.length} items`;

  if (!items.length) {
    container.innerHTML = `
      <div class="review-queue-item selected">
        <div class="rq-top">
          <div class="rq-file">No review items available</div>
          <div class="rq-confidence">0%</div>
        </div>
        <div class="rq-sub">Current backend artifacts returned an empty review queue</div>
        <div class="rq-status pending">Empty</div>
      </div>
    `;
    if (completeBanner) completeBanner.style.display = "none";
    return;
  }

  items.forEach((item, idx) => {
    const row = document.createElement("div");
    row.className = `review-queue-item ${idx === reviewIndex ? "selected" : ""}`;
    row.onclick = () => {
      reviewIndex = idx;
      renderReviewQueue();
      renderReviewViewer();
    };

    row.innerHTML = `
      <div class="rq-top">
        <div class="rq-file">${item.filename}</div>
        <div class="rq-confidence">${item.confidence}%</div>
      </div>
      <div class="rq-sub">${item.species} · ${item.camera}</div>
      <div class="rq-status ${item.status}">${capitalize(item.status)}</div>
    `;

    container.appendChild(row);
  });

  const allDone = reviewItems.length > 0 && reviewItems.every((x) => x.status === "confirmed" || x.status === "flagged");
  if (completeBanner) completeBanner.style.display = allDone ? "block" : "none";
}

function renderReviewViewer() {
  const items = getFilteredReviewItems();
  if (!items.length) {
    setText("viewer-img", "—");
    setText("viewer-filename", "No review items");
    setText("viewer-pos", "0 of 0");
    setText("nav-counter", "0 / 0");
    setText("conf-overlay", "0% confidence");
    setText("species-name", "Nothing pending");
    setText("species-certainty", "Review queue is empty");
    setText("meta-filename", "—");
    setText("meta-burst", "—");
    setText("meta-status", "Empty");
    const humanOverlay = document.getElementById("human-overlay");
    if (humanOverlay) humanOverlay.style.display = "none";
    setHTML("det-animal", `<span style="font-size:14px;line-height:1;font-weight:500">—</span>No`);
    setHTML("det-human", `<span style="font-size:14px;line-height:1;font-weight:500">—</span>No`);
    setHTML("review-meta", `
      <div class="meta-row"><span class="meta-key">Source</span><span class="meta-val">speciesnet_review.csv</span></div>
      <div class="meta-row"><span class="meta-key">Status</span><span class="meta-val">No rows returned</span></div>
    `);
    return;
  }

  if (reviewIndex >= items.length) reviewIndex = 0;
  const item = items[reviewIndex];

  const viewerImg = document.getElementById("viewer-img");
  const filename = document.getElementById("viewer-filename");
  const pos = document.getElementById("viewer-pos");
  const navCounter = document.getElementById("nav-counter");
  const conf = document.getElementById("conf-overlay");
  const humanOverlay = document.getElementById("human-overlay");
  const detAnimal = document.getElementById("det-animal");
  const detHuman = document.getElementById("det-human");
  const speciesName = document.getElementById("species-name");
  const speciesCertainty = document.getElementById("species-certainty");
  const metaFilename = document.getElementById("meta-filename");
  const metaBurst = document.getElementById("meta-burst");
  const metaStatus = document.getElementById("meta-status");

  if (viewerImg) viewerImg.textContent = item.emoji;
  if (filename) filename.textContent = item.filename;
  if (pos) pos.textContent = `${reviewIndex + 1} of ${items.length}`;
  if (navCounter) navCounter.textContent = `${reviewIndex + 1} / ${items.length}`;
  if (conf) conf.textContent = `${item.confidence}% confidence`;
  if (humanOverlay) humanOverlay.style.display = item.humanDetected ? "inline-flex" : "none";

  if (detAnimal) {
    detAnimal.innerHTML = item.animalDetected
      ? `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="9 12 11 14 15 10"/></svg>Yes`
      : `<span style="font-size:14px;line-height:1;font-weight:500">—</span>No`;
  }

  if (detHuman) {
    detHuman.innerHTML = item.humanDetected
      ? `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="9 12 11 14 15 10"/></svg>Yes`
      : `<span style="font-size:14px;line-height:1;font-weight:500">—</span>No`;
  }

  if (speciesName) speciesName.textContent = item.species;
  if (speciesCertainty) speciesCertainty.textContent = `${item.confidence}% model certainty`;
  if (metaFilename) metaFilename.textContent = item.filename;
  if (metaBurst) metaBurst.textContent = item.burst;
  if (metaStatus) metaStatus.innerHTML = item.status === "pending"
    ? `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>Pending`
    : capitalize(item.status);

  const meta = document.getElementById("review-meta");
  if (meta) {
    meta.innerHTML = `
      <div class="meta-row"><span class="meta-key">Filename</span><span class="meta-val">${item.filename}</span></div>
      <div class="meta-row"><span class="meta-key">Camera</span><span class="meta-val">${item.camera}</span></div>
      <div class="meta-row"><span class="meta-key">Date / Time</span><span class="meta-val">${item.datetime}</span></div>
      <div class="meta-row"><span class="meta-key">Burst Group</span><span class="meta-val">${item.burst}</span></div>
      <div class="meta-row"><span class="meta-key">Status</span><span class="meta-val">${capitalize(item.status)}</span></div>
    `;
  }
}

function navigateReview(direction) {
  const items = getFilteredReviewItems();
  if (!items.length) return;

  reviewIndex += direction;
  if (reviewIndex < 0) reviewIndex = items.length - 1;
  if (reviewIndex >= items.length) reviewIndex = 0;

  renderReviewQueue();
  renderReviewViewer();
}

function reviewAction(action) {
  const items = getFilteredReviewItems();
  const item = items[reviewIndex];
  if (!item) return;

  const original = item.status;
  item.status = action === "confirm" ? "confirmed" : "flagged";

  lastUndoAction = {
    type: "review-status",
    itemId: item.id,
    oldStatus: original
  };

  showUndoToast(action === "confirm" ? "Confirmed" : "Flagged");
  renderReviewQueue();
  renderReviewViewer();
}

function askFlagConfirm() {
  openConfirmModal({
    title: "Flag this image?",
    body: "This image will be marked as uncertain for later review.",
    kind: "warn",
    onConfirm: () => reviewAction("flag")
  });
}

function setRFilter(el, value) {
  reviewFilter = value;
  reviewIndex = 0;

  document.querySelectorAll(".rfilter-chip").forEach((chip) => chip.classList.remove("active"));
  el.classList.add("active");

  renderReviewQueue();
  renderReviewViewer();
}

function toggleHumanFilter(el) {
  humanFilterOnly = !humanFilterOnly;
  el.classList.toggle("active", humanFilterOnly);
  reviewIndex = 0;
  renderReviewQueue();
  renderReviewViewer();
}

function toggleSort(btn) {
  sortMode = sortMode === "low-confidence" ? "default" : "low-confidence";
  btn.innerHTML = sortMode === "low-confidence"
    ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="15" y2="12"/><line x1="3" y1="18" x2="9" y2="18"/></svg>Low confidence first`
    : `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="15" y2="12"/><line x1="3" y1="18" x2="9" y2="18"/></svg>Default order`;

  renderReviewQueue();
  renderReviewViewer();
}

function toggleBurstView() {
  burstViewEnabled = document.getElementById("burst-toggle")?.checked ?? true;
}

function openSpeciesEdit() {
  const display = document.getElementById("species-display");
  const edit = document.getElementById("species-edit");
  const select = document.getElementById("species-select");
  const items = getFilteredReviewItems();
  const item = items[reviewIndex];
  if (!item) return;

  if (display) display.style.display = "none";
  if (edit) edit.style.display = "block";
  if (select) select.value = item.species;
}

function saveSpeciesEdit() {
  const select = document.getElementById("species-select");
  const items = getFilteredReviewItems();
  const item = items[reviewIndex];
  if (!item || !select) return;

  item.species = select.value;
  cancelSpeciesEdit();
  renderReviewViewer();
  showToast("Species updated", "success");
}

function cancelSpeciesEdit() {
  const display = document.getElementById("species-display");
  const edit = document.getElementById("species-edit");
  if (display) display.style.display = "flex";
  if (edit) edit.style.display = "none";
}

function showUndoToast(message) {
  const toast = document.getElementById("undo-toast");
  const msg = document.getElementById("undo-toast-msg");
  if (!toast || !msg) return;

  msg.textContent = `✓ ${message}`;
  toast.classList.add("show");
  setTimeout(() => {
    toast.classList.remove("show");
  }, 4000);
}

function undoLastAction() {
  if (!lastUndoAction) return;

  if (lastUndoAction.type === "review-status") {
    const item = reviewItems.find((x) => x.id === lastUndoAction.itemId);
    if (item) item.status = lastUndoAction.oldStatus;
  }

  if (lastUndoAction.type === "burst-action") {
    document.getElementById("burst-result-banner")?.classList.remove("show");
    const actions = document.getElementById("burst-action-buttons");
    if (actions) actions.style.display = "block";
  }

  lastUndoAction = null;
  renderReviewQueue();
  renderReviewViewer();
  showToast("Action undone", "success");
}

function askBurstConfirm(kind) {
  const textMap = {
    keep: "Keep only the best image from this burst group?",
    exclude: "Exclude this entire burst group from export?"
  };

  openConfirmModal({
    title: "Apply burst action?",
    body: textMap[kind] || "Apply action to burst group?",
    kind: kind === "exclude" ? "danger" : "warn",
    onConfirm: () => burstAction(kind)
  });
}

function burstAction(kind) {
  if (kind === "expand") {
    showToast("Burst group expanded", "success");
    return;
  }

  const banner = document.getElementById("burst-result-banner");
  const title = document.getElementById("burst-result-title");
  const sub = document.getElementById("burst-result-sub");
  const actions = document.getElementById("burst-action-buttons");

  if (title) title.textContent = kind === "keep" ? "Best image kept" : "Burst group excluded";
  if (sub) sub.textContent = kind === "keep"
    ? "Only the highest-confidence frame will be exported."
    : "All images in this burst group will be excluded from export.";

  if (banner) banner.classList.add("show");
  if (actions) actions.style.display = "none";

  lastUndoAction = { type: "burst-action" };
}

function undoBurstAction() {
  undoLastAction();
}

function normalizeReviewItem(item) {
  const species = (item?.species || "Unknown").trim() || "Unknown";
  const speciesLower = species.toLowerCase();

  return {
    id: item?.id,
    filename: item?.filename || `review-item-${item?.id || "unknown"}`,
    species,
    confidence: Number(item?.confidence || 0),
    animalDetected: !["blank", "human", "vehicle", "no cv result"].includes(speciesLower),
    humanDetected: speciesLower.includes("human"),
    camera: item?.camera || "Unknown",
    datetime: item?.datetime || "Unknown",
    burst: item?.reason ? `Reason: ${item.reason}` : "Manual review item",
    status: item?.status || "pending",
    emoji: getSpeciesEmoji(speciesLower),
    reason: item?.reason || ""
  };
}

async function loadReviewData() {
  const container = document.getElementById("review-queue-list");
  const count = document.getElementById("queue-count");
  if (container) {
    container.innerHTML = `<div class="review-queue-item selected"><div class="rq-file">Loading review queue…</div></div>`;
  }
  if (count) count.textContent = "Loading…";

  try {
    const items = await getReviewItems();
    reviewItems = Array.isArray(items) ? items.map(normalizeReviewItem) : [];
    reviewIndex = 0;
    renderReviewQueue();
    renderReviewViewer();
    pageLoadState.review = true;
  } catch (error) {
    reviewItems = [];
    renderReviewQueue();
    renderReviewViewer();
    showToast(error.message || "Unable to load review items", "warn");
  }
}

// =========================
// VALIDATE
// =========================
function renderAffectedImages(data = validationData) {
  const body = document.getElementById("affected-table-body");
  if (!body) return;

  const files = (data?.files || []).filter((item) => Number(item.outside_range || 0) > 0);
  if (!files.length) {
    body.innerHTML = `
      <tr>
        <td colspan="4" style="color:var(--muted)">No out-of-range rows were reported by the current validation artifacts.</td>
      </tr>
    `;
    return;
  }

  body.innerHTML = files.map((item) => `
    <tr>
      <td>${escapeHtml(item.file)}</td>
      <td>${escapeHtml(formatCameraName(item.file))}</td>
      <td>Not available in current validation output</td>
      <td>${formatNumber(item.outside_range)} row(s) flagged outside deployment interval</td>
    </tr>
  `).join("");
}

function toggleAffectedPanel() {
  const panel = document.getElementById("affected-panel");
  const btn = document.getElementById("affected-toggle-btn");
  const chev = document.getElementById("affected-btn-chevron");
  if (!panel) return;

  const open = panel.classList.contains("open");
  panel.classList.toggle("open", !open);
  if (btn) btn.classList.toggle("open", !open);
  if (chev) chev.style.transform = !open ? "rotate(90deg)" : "rotate(0deg)";
}

function updateTimePreview(value) {
  const after = document.getElementById("time-preview-after");
  if (!after) return;
  const hrs = Number(value || 0);
  after.textContent = `After: 2024-03-10 ${String(1 + hrs).padStart(2, "0")}:30:00`;
}

function renderUnprocessedImages(data = validationData) {
  const body = document.getElementById("unproc-table-body");
  if (!body) return;

  const unprocessed = Number(data?.unprocessed || 0);
  if (!unprocessed) {
    body.innerHTML = `
      <tr>
        <td colspan="4" style="color:var(--muted)">All manifest rows have corresponding ML output rows.</td>
      </tr>
    `;
    return;
  }

  body.innerHTML = `
    <tr>
      <td>manifest.csv</td>
      <td>All locations</td>
      <td>Not available in current validation output</td>
      <td>${formatNumber(unprocessed)} image(s) are missing rows in ml_outputs.csv</td>
    </tr>
  `;
}

function toggleUnprocPanel() {
  const panel = document.getElementById("unproc-panel");
  if (!panel) return;
  panel.classList.toggle("open");
}

function applyValidationData(data) {
  validationData = data;

  const totalRecords = Number((data?.files || []).reduce((sum, item) => sum + Number(item.rows || 0), 0));
  const warnings = Number(data?.outside_range || 0) + Number(data?.column_issue_count || 0);
  const errors = Number(data?.unprocessed || 0);
  const valid = Math.max(totalRecords - warnings, 0);

  setText("val-total-records", formatNumber(totalRecords));
  setText("val-valid-records", formatNumber(valid));
  setText("val-warning-count", formatNumber(warnings));
  setText("val-error-count", formatNumber(errors));

  const rangeWarnBox = document.getElementById("range-warn-box");
  if (rangeWarnBox) rangeWarnBox.style.display = Number(data?.outside_range || 0) > 0 ? "flex" : "none";
  setText("range-warn-title", `${formatNumber(data?.outside_range || 0)} images outside deployment range`);
  setHTML(
    "range-warn-body",
    Number(data?.outside_range || 0) > 0
      ? `Current output files include rows flagged as <strong>outside deployment interval</strong>.`
      : `No generated output rows are outside the deployment range.`
  );
  setText(
    "val-sub-datetime",
    Number(data?.outside_range || 0) > 0
      ? "Some rows are flagged outside the deployment interval"
      : "No rows are outside the deployment interval"
  );
  setText("val-badge-datetime", `${formatNumber(data?.outside_range || 0)} outside range`);
  setText(
    "val-sub-unprocessed",
    errors
      ? "Some manifest images do not have corresponding ML output rows"
      : "All manifest images have matching ML output rows"
  );
  setText("val-badge-unprocessed", `${formatNumber(errors)} unprocessed`);
  setText("unproc-panel-title", `${formatNumber(errors)} images — ML processing incomplete`);
  setText(
    "unproc-panel-sub",
    errors
      ? "These manifest images are missing ML output rows and will not be included in export artifacts."
      : "No missing ML output rows were found."
  );
  setText("val-run-note", data ? "Last validated: Current pipeline artifacts" : "Validation data unavailable");

  renderAffectedImages(data);
  renderUnprocessedImages(data);
}

async function loadValidationData({ showToastOnError = false } = {}) {
  try {
    const data = await getValidationIssues();
    applyValidationData(data);
    pageLoadState.validate = true;
    return data;
  } catch (error) {
    applyValidationData(null);
    if (showToastOnError) {
      showToast(error.message || "Unable to load validation issues", "warn");
    }
    return null;
  }
}

async function runValidation() {
  const data = await loadValidationData({ showToastOnError: true });
  if (data) {
    if (currentPage === "dashboard" && dashboardSummary) {
      applyDashboardSummary(dashboardSummary, data, exportData);
    }
    if (currentPage === "export") {
      applyExportData(exportData, data);
    }
    showToast("Validation refreshed from current output artifacts", "success");
  }
}

// =========================
// EXPORT
// =========================
function selectFormat(format) {
  selectedFormat = format;

  document.querySelectorAll(".export-fmt-card").forEach((card) => card.classList.remove("selected"));
  document.getElementById(`fmt-${format}`)?.classList.add("selected");

  syncExportFilenamePreview();
}

function toggleExportOption(row, id, checkboxEl = null) {
  const cb = checkboxEl || row.querySelector(".export-option-cb");
  if (!cb) return;

  if (!checkboxEl) cb.checked = !cb.checked;
  row.classList.toggle("checked", cb.checked);
}

function toggleExportFilter() {
  const body = document.getElementById("export-filter-body");
  const label = document.getElementById("filter-status-label");
  const chev = document.getElementById("filter-chevron");
  if (!body) return;

  const open = body.classList.contains("open");
  body.classList.toggle("open", !open);

  if (label) label.textContent = !open ? "On — custom filter applied" : "Off — exporting all dates";
  if (chev) chev.style.transform = !open ? "rotate(180deg)" : "rotate(0deg)";
}

function syncExportFilenamePreview() {
  const input = document.getElementById("export-filename");
  const preview = document.getElementById("export-filename-preview");
  if (!input || !preview) return;

  preview.textContent = `${input.value}.${selectedFormat}`;
}

document.addEventListener("input", (e) => {
  if (e.target.id === "export-filename") {
    syncExportFilenamePreview();
  }
});

async function startExport() {
  if (!driveConnected) {
    showToast("Connect Google Drive first", "warn");
    return;
  }

  if (!validationData) {
    await loadValidationData();
  }

  const hasIssues = Number(validationData?.outside_range || 0) > 0
    || Number(validationData?.unprocessed || 0) > 0
    || Number(validationData?.column_issue_count || 0) > 0;

  if (hasIssues) {
    const modal = document.getElementById("export-modal-overlay");
    if (modal) modal.classList.add("active");
    return;
  }

  void beginExport();
}

function closeExportModal(event) {
  if (event && event.target !== event.currentTarget) return;
  document.getElementById("export-modal-overlay")?.classList.remove("active");
}

function confirmExport() {
  closeExportModal();
  void beginExport();
}

function buildExportFolderRows(files = []) {
  if (!files.length) {
    return `
      <div class="export-folder-row">
        <div class="export-folder-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#718096" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
        </div>
        <div style="flex:1;min-width:0">
          <div class="export-folder-name">No export files available</div>
          <div class="export-folder-sub">Run the pipeline to generate data/outputs/by_location files.</div>
        </div>
      </div>
    `;
  }

  return files.map((file) => `
    <div class="export-folder-row">
      <div class="export-folder-icon">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#2B6CB0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
      </div>
      <div style="flex:1;min-width:0">
        <div class="export-folder-name">${escapeHtml(formatCameraName(file.name))}</div>
        <div class="export-folder-sub">${formatNumber(file.rows)} rows · ${escapeHtml(file.path || file.name)}</div>
      </div>
      <div class="export-folder-actions">
        <span class="export-sync-badge synced">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          Ready
        </span>
        <button class="export-folder-view-btn" onclick="showToast(this.dataset.path,'')" data-path="${escapeHtml(file.path || file.name)}">View Artifact</button>
      </div>
    </div>
  `).join("");
}

function applyExportData(data, validation = validationData) {
  exportData = data;

  const files = data?.files || [];
  const issueCount = Number(validation?.outside_range || 0)
    + Number(validation?.unprocessed || 0)
    + Number(validation?.column_issue_count || 0);
  const issueGroups = [validation?.outside_range, validation?.unprocessed, validation?.column_issue_count]
    .filter((value) => Number(value || 0) > 0).length;

  const banner = document.getElementById("export-status-banner");
  if (banner) banner.classList.toggle("warn", issueCount > 0);

  setText(
    "export-status-title",
    issueCount > 0
      ? `${formatNumber(issueGroups)} validation issue group${issueGroups === 1 ? "" : "s"} found`
      : "Validation checks are clear"
  );
  setText(
    "export-status-sub",
    issueCount > 0
      ? `${formatNumber(validation?.unprocessed || 0)} unprocessed images and ${formatNumber(validation?.outside_range || 0)} out-of-range rows will be excluded from export artifacts.`
      : "Current export artifacts are ready with no validation exclusions."
  );

  setText("export-records-val", formatNumber(data?.total_rows || 0));
  setText("export-humans-val", "N/A");
  setText("export-duplicates-val", "N/A");
  const exportSummarySubs = document.querySelectorAll(".export-summary-sub");
  if (exportSummarySubs[0]) {
    exportSummarySubs[0].textContent = data?.status === "ready"
      ? "Rows present in generated by_location CSV files"
      : "No generated export rows found";
  }
  if (exportSummarySubs[1]) {
    exportSummarySubs[1].textContent = "Not available from current backend export payload";
  }
  if (exportSummarySubs[2]) {
    exportSummarySubs[2].textContent = "Not available from current backend export payload";
  }

  setText("export-option-duplicates-badge", "Not available");
  setText("export-option-humans-badge", "Not available");
  setText("export-option-split-badge", `${formatNumber(data?.file_count || 0)} file${Number(data?.file_count || 0) === 1 ? "" : "s"}`);

  const folderList = document.getElementById("export-folder-list");
  if (folderList) folderList.innerHTML = buildExportFolderRows(files);

  setText("export-output-folder-name", data?.output_dir || "data/outputs/by_location");
  setText("export-output-folder-email", signedInUser?.email || getDriveProfile().driveEmail);

  const exportButton = document.getElementById("export-main-btn");
  if (exportButton) {
    exportButton.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
      Export ${formatNumber(data?.total_rows || 0)} Records to Google Drive
    `;
  }

  const exportMainNote = document.getElementById("export-main-note");
  if (exportMainNote) {
    const inputValue = document.getElementById("export-filename")?.value || "export";
    exportMainNote.innerHTML = data
      ? `File name preview: <strong id="export-filename-preview">${escapeHtml(inputValue)}.${escapeHtml(selectedFormat)}</strong> · ${formatNumber(data.file_count || 0)} artifact file(s) in <strong>${escapeHtml(data.output_dir || "data/outputs/by_location")}</strong>`
      : `File will be saved as <strong id="export-filename-preview">${escapeHtml(inputValue)}.${escapeHtml(selectedFormat)}</strong>`;
  }

  const modalBody = document.getElementById("export-modal-body");
  if (modalBody) {
    modalBody.innerHTML = issueCount > 0
      ? `Your dataset has <strong>${formatNumber(issueGroups)}</strong> unresolved validation issue group(s). Affected rows will be excluded from the generated export artifacts.`
      : `Current export artifacts are ready. Upload to Google Drive is not yet wired, so this action returns the generated files only.`;
  }

  setHTML(
    "export-modal-issue",
    `
      <strong>${formatNumber(validation?.unprocessed || 0)} images</strong> — missing ML output rows<br>
      <strong>${formatNumber(validation?.outside_range || 0)} rows</strong> — outside deployment interval<br>
      <strong>${formatNumber(validation?.column_issue_count || 0)} checks</strong> — missing required columns
    `
  );
}

async function loadExportData({ showToastOnError = false } = {}) {
  try {
    const [validation, data] = await Promise.all([
      validationData ? Promise.resolve(validationData) : getValidationIssues(),
      startExportRequest()
    ]);
    if (!validationData) {
      applyValidationData(validation);
    }
    applyExportData(data, validation);
    pageLoadState.export = true;
    return data;
  } catch (error) {
    applyExportData(null, validationData);
    if (showToastOnError) {
      showToast(error.message || "Unable to load export artifacts", "warn");
    }
    return null;
  }
}

async function beginExport() {
  const wrap = document.getElementById("export-progress-wrap");
  const fill = document.getElementById("export-progress-fill");
  const pct = document.getElementById("export-progress-pct");
  const text = document.getElementById("export-progress-text");
  const sub = document.getElementById("export-progress-sub");

  exportInProgress = true;
  if (wrap) wrap.style.display = "block";
  if (fill) fill.style.width = "20%";
  if (pct) pct.textContent = "20%";
  if (text) text.textContent = "Reading export artifacts…";
  if (sub) sub.textContent = "Inspecting generated by_location CSV files…";

  try {
    const data = await startExportRequest();
    applyExportData(data, validationData);
    if (fill) fill.style.width = "100%";
    if (pct) pct.textContent = "100%";
    if (text) text.textContent = data?.status === "ready" ? "Export artifacts ready" : "No export artifacts available";
    if (sub) sub.textContent = data?.note || "Upload integration is not wired yet.";
    showToast(data?.message || "Export artifacts refreshed", data?.status === "ready" ? "success" : "warn");
  } catch (error) {
    if (fill) fill.style.width = "0%";
    if (pct) pct.textContent = "0%";
    if (text) text.textContent = "Unable to load export artifacts";
    if (sub) sub.textContent = error.message || "Backend request failed";
    showToast(error.message || "Unable to load export artifacts", "warn");
  } finally {
    exportInProgress = false;
  }
}

async function loadPageData(pageName) {
  if (pageName === "upload") {
    await loadPipelineStatus({ silent: true });
    if (driveConnected) {
      await Promise.all([
        hydrateDriveFolderSelection({ silent: true }),
        loadDriveSyncStatus({ silent: true })
      ]);
    }
    return;
  }

  if (pageName === "dashboard") {
    await Promise.all([
      loadValidationData(),
      loadDashboardData()
    ]);
    if (dashboardSummary) {
      applyDashboardSummary(dashboardSummary, validationData, exportData);
    }
    return;
  }

  if (pageName === "review") {
    await loadReviewData();
    return;
  }

  if (pageName === "model") {
    const [status] = await Promise.all([
      loadPipelineStatus({ silent: true }),
      driveConnected ? loadDriveSyncStatus({ silent: true }) : Promise.resolve(null)
    ]);
    runningModel = status?.status === "running";
    return;
  }

  if (pageName === "validate") {
    const data = await loadValidationData({ showToastOnError: true });
    if (data && dashboardSummary) {
      applyDashboardSummary(dashboardSummary, data, exportData);
    }
    return;
  }

  if (pageName === "export") {
    const data = await loadExportData({ showToastOnError: true });
    if (data && dashboardSummary) {
      applyDashboardSummary(dashboardSummary, validationData, data);
    }
  }
}

// =========================
// DATE PICKERS
// =========================
function buildDatePickers() {
  const ids = ["start", "end", "export-start", "export-end"];
  ids.forEach((id) => {
    const popup = document.getElementById(`dp-popup-${id}`);
    if (!popup) return;

    popup.innerHTML = `
      <div class="dp-inner">
        <div class="dp-head">
          <strong>March 2026</strong>
        </div>
        <div class="dp-grid">
          ${Array.from({ length: 30 }, (_, i) => `
            <button type="button" class="dp-day" onclick="pickDate('${id}','Mar ${i + 1}, 2026')">${i + 1}</button>
          `).join("")}
        </div>
      </div>
    `;
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".dp-wrap")) {
      closeAllDatePickers();
    }
  });
}

function enterDashboard() {
  const loginScreen = document.getElementById("login-screen");
  const mainApp = document.getElementById("main-app");

  setDriveModalVisible(false);
  if (loginScreen) loginScreen.style.display = "none";
  if (mainApp) mainApp.style.display = "flex";
}

function returnToLogin() {
  const loginScreen = document.getElementById("login-screen");
  const mainApp = document.getElementById("main-app");

  setDriveModalVisible(false);
  if (loginScreen) loginScreen.style.display = "flex";
  if (mainApp) mainApp.style.display = "none";
}

function clearOAuthQueryParams() {
  const url = new URL(window.location.href);
  url.searchParams.delete("google_auth");
  window.history.replaceState({}, document.title, url.toString());
}

async function bootstrapAppState() {
  const oauthResult = new URLSearchParams(window.location.search).get("google_auth");
  const token = localStorage.getItem("token");

  if (!token) {
    returnToLogin();
    if (oauthResult) {
      clearOAuthQueryParams();
    }
    return;
  }

  try {
    const user = await getCurrentUser();
    let googleAuth = { authenticated: false, user: null };
    let driveStatus = {
      connected: false,
      drive_name: null,
      drive_email: null,
      selected_folder: null
    };

    const [googleAuthResult, driveStatusResult] = await Promise.allSettled([
      getGoogleAuthStatus(),
      getDriveStatus()
    ]);

    if (googleAuthResult.status === "fulfilled") {
      googleAuth = googleAuthResult.value;
    }

    if (driveStatusResult.status === "fulfilled") {
      driveStatus = driveStatusResult.value;
    }

    signedInUser = user || null;
    if (googleAuth?.authenticated && googleAuth?.user?.email) {
      signedInUser = {
        ...(user || {}),
        email: googleAuth.user.email
      };
    }

    if (signedInUser?.project) {
      selectedProject = signedInUser.project;
    }

    applyBackendDriveState(googleAuth, driveStatus);
    availableDriveFolders = [];
    driveFoldersLoading = false;
    driveFolderError = "";
    updateDriveConfirmation();
    syncDriveUI();
    renderDriveFolderSelection();
    updateDriveSyncPollingState();
    await loadPipelineStatus({ silent: true });

    if (googleAuthActive && driveConnected) {
      enterDashboard();
      await hydrateDriveFolderSelection({ silent: true });
      if (selectedDriveFolder?.id) {
        showPage("dashboard");
        await loadPageData("dashboard");
      } else {
        switchUploadTab("drive");
        showPage("upload");
      }
      if (oauthResult === "success") {
        showToast("Google sign-in successful", "success");
      }
    } else if (googleAuthActive) {
      returnToLogin();
      goToStep3();
      setDriveModalVisible(true);
      if (oauthResult === "success") {
        showToast("Google sign-in successful. Confirm the project drive to continue.", "success");
      }
    } else {
      enterDashboard();
      await loadPageData("dashboard");
      if (oauthResult === "error") {
        showToast("Google sign-in failed. Local mode is still available.", "warn");
      }
    }
  } catch (error) {
    driveConnected = false;
    signedInUser = null;
    googleAuthActive = false;
    googleAuthUser = null;
    selectedDriveFolder = null;
    applySelectedDriveFolderSettings(null);
    driveFolderError = "";
    currentDriveProfile = getDriveProfile();
    localStorage.removeItem("token");
    applyDriveSyncStatus(null);
    updateDriveConfirmation();
    syncDriveUI();
    renderDriveFolderSelection();
    returnToLogin();
    setLoginStep(2);
  } finally {
    if (oauthResult) {
      clearOAuthQueryParams();
    }
  }
}

function openDP(id) {
  closeAllDatePickers();
  activeDatePicker = id;
  document.getElementById(`dp-popup-${id}`)?.classList.add("open");
}

function closeAllDatePickers() {
  document.querySelectorAll(".dp-popup").forEach((el) => el.classList.remove("open"));
  activeDatePicker = null;
}

function pickDate(id, value) {
  const input = document.getElementById(`dp-text-${id}`);
  if (input) input.value = value;
  closeAllDatePickers();
}

// =========================
// CONFIRM MODAL
// =========================
function openConfirmModal({ title, body, kind, onConfirm }) {
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

  if (overlay) overlay.classList.add("active");
}

function closeConfirmModal(event) {
  if (event && event.target !== event.currentTarget) return;
  document.getElementById("confirm-modal-overlay")?.classList.remove("active");
  activeModalAction = null;
}

function confirmModalOK() {
  const fn = activeModalAction;
  closeConfirmModal();
  if (typeof fn === "function") fn();
}

// =========================
// TOASTS
// =========================
function showToast(message, type = "") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast ${type}`.trim();
  toast.textContent = message;

  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("show");
  }, 10);

  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 220);
  }, 2600);
}

// =========================
// HELPERS
// =========================
function capitalize(value) {
  if (!value) return "";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

// =========================
// GLOBALS FOR INLINE HTML
// =========================
window.showPage = showPage;
window.showPageFromReview = showPageFromReview;

window.selectProject = selectProject;
window.goToStep1 = goToStep1;
window.goToStep2 = goToStep2;
window.goToStep3 = goToStep3;
window.simulateOAuth = simulateOAuth;
window.confirmDrive = confirmDrive;
window.switchAccount = switchAccount;
window.openDriveModal = openDriveModal;
window.reconnectDrive = reconnectDrive;
window.triggerSync = triggerSync;
window.loadDriveSyncStatus = loadDriveSyncStatus;

window.switchUploadTab = switchUploadTab;
window.togglePause = togglePause;
window.selectLocCard = selectLocCard;
window.handleDriveFolderSelect = handleDriveFolderSelect;
window.handleDriveSyncSettingsChange = handleDriveSyncSettingsChange;
window.refreshDriveFolders = refreshDriveFolders;
window.syncDriveManualSelectionState = syncDriveManualSelectionState;
window.handleDriveManualSelectionKeydown = handleDriveManualSelectionKeydown;
window.applyManualDriveFolderSelection = applyManualDriveFolderSelection;

window.updateSlider = updateSlider;
window.toggleRunModel = toggleRunModel;
window.toggleDriveRunModel = toggleDriveRunModel;
window.toggleRunDetail = toggleRunDetail;

window.navigateReview = navigateReview;
window.reviewAction = reviewAction;
window.askFlagConfirm = askFlagConfirm;
window.setRFilter = setRFilter;
window.toggleHumanFilter = toggleHumanFilter;
window.toggleSort = toggleSort;
window.toggleBurstView = toggleBurstView;
window.openSpeciesEdit = openSpeciesEdit;
window.saveSpeciesEdit = saveSpeciesEdit;
window.cancelSpeciesEdit = cancelSpeciesEdit;
window.undoLastAction = undoLastAction;
window.askBurstConfirm = askBurstConfirm;
window.burstAction = burstAction;
window.undoBurstAction = undoBurstAction;

window.toggleAffectedPanel = toggleAffectedPanel;
window.updateTimePreview = updateTimePreview;
window.toggleUnprocPanel = toggleUnprocPanel;
window.runValidation = runValidation;

window.selectFormat = selectFormat;
window.toggleExportOption = toggleExportOption;
window.toggleExportFilter = toggleExportFilter;
window.startExport = startExport;
window.closeExportModal = closeExportModal;
window.confirmExport = confirmExport;

window.openDP = openDP;
window.pickDate = pickDate;

window.closeConfirmModal = closeConfirmModal;
window.confirmModalOK = confirmModalOK;
window.showToast = showToast;
