/** Shared mutable state for the browser-native feature modules. */
export const DRIVE_FOLDER_SOURCE_LABELS = {
  my_drive: "My Drive",
  shared: "Shared",
  shortcut: "Shortcut"
};

export const DRIVE_MANUAL_FOLDER_HINT =
  "Paste a Google Drive folder link or raw folder ID if it doesn’t appear in the dropdown.";

export const projectLabels = {
  uci: "Field Research Program",
  other: "Shared Wildlife Survey"
};

export const driveProfiles = {
  uci: {
    driveName: "Field Camera Archive",
    driveEmail: "field.research@example.org",
    projectLabel: "Field Research Program"
  },
  other: {
    driveName: "Shared Wildlife Survey Archive",
    driveEmail: "survey.team@example.org",
    projectLabel: "Shared Wildlife Survey"
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
  usingMockAuth: false,
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
