/** Shared mutable state for the browser-native feature modules. */
export const DRIVE_FOLDER_SOURCE_LABELS = {
  my_drive: "My Drive",
  shared: "Shared",
  shortcut: "Shortcut"
};

export const DRIVE_MANUAL_FOLDER_HINT =
  "Paste a Google Drive folder link or raw folder ID if it doesn’t appear in the dropdown.";

export const projectLabels = {
  uci: "UCI Nature Wildlife Camera Project"
};

export const driveProfiles = {
  uci: {
    driveName: "UCI Nature Wildlife Drive",
    driveEmail: "",
    projectLabel: "UCI Nature Wildlife Camera Project"
  }
};

export function createEmptyDriveSyncState() {
  return {
    status: "idle",
    source_ready: false,
    started_at: null,
    finished_at: null,
    folder: null,
    selected_folder: null,
    selected_folder_matches: false,
    available_count: 0,
    discovered_count: 0,
    downloaded_count: 0,
    remaining_count: 0,
    progress_percent: 0,
    // Performance metrics emitted by the backend during a parallel sync.
    failed_count: 0,
    skipped_count: 0,
    discovery_complete: false,
    cancellation_requested: false,
    // The user's selected sync limit ("All files" → 0). Used as the
    // progress denominator while discovery is still in progress so the
    // percent reflects progress toward the requested target.
    requested_total: 0,
    images_per_second: null,
    eta_seconds: null,
    elapsed_seconds: null,
    current_file: null,
    staging_dir: null,
    drive_index_path: null,
    error: null,
    last_sync_message: null
  };
}

/** Shared application state for the static browser UI. */
export const appState = {
  currentPage: "dashboard",
  selectedProject: "uci",
  backendHealth: {
    connected: false,
    pipelineRuntimeReady: false,
    detail: "",
    checkedAt: null
  },
  driveConnected: false,
  selectedFormat: "csv",
  uploadTab: "manual",
  sidebarCollapsed: false,
  uploadPaused: false,
  runningModel: false,
  exportInProgress: false,
  reviewIndex: 0,
  reviewFilter: "all",
  humanFilterOnly: false,
  burstViewEnabled: true,
  sortMode: "low-confidence",
  activeDatePicker: null,
  signedInUser: null,
  currentDriveProfile: null,
  googleAuthActive: false,
  googleAuthUser: null,
  pipelineStatus: null,
  pipelineResults: null,
  availableDriveFolders: [],
  selectedDriveFolder: null,
  driveFoldersLoading: false,
  driveFolderError: "",
  driveSyncState: createEmptyDriveSyncState(),
  driveCameraLocation: "",
  driveCreateSiteMode: false,
  driveSyncLimit: null,
  driveDateRangeStart: "",
  driveDateRangeEnd: "",
  driveFlagOutsideRange: false,
  driveManualSelectionFeedback: null,
  driveManualSelectionPending: false,
  reviewItems: [],
  dashboardSummary: null,
  validationData: null,
  exportData: null,
  pageLoadState: {
    dashboard: false,
    review: false,
    validate: false,
    export: false
  },
  lastUndoAction: null,
  charts: {
    species: null,
    timeline: null
  }
};
