/** App bootstrap helper for exposing legacy window callbacks expected by the markup. */
import { closeConfirmModal, confirmModalOK } from "../components/common/confirmModal.js";
import { openDP, pickDate, dpNav } from "../components/common/datePickers.js";

export function bindGlobals(app, showPage) {
  app.showPage = showPage;
  window.showPage = showPage;
  window.showPageFromReview = showPage;
  window.showToast = app.showToast;
  window.closeConfirmModal = closeConfirmModal;
  window.confirmModalOK = confirmModalOK;
  window.openDP = openDP;
  window.dpNav = dpNav;
  window.pickDate = pickDate;
  window.selectProject = app.features.auth.selectProject;
  window.goToStep2 = () => app.features.auth.setLoginStep(2);
  window.startGoogleSignIn = app.features.auth.startGoogleSignIn;
  window.continueWithoutGoogleDrive = app.features.auth.continueWithoutGoogleDrive;
  window.confirmDrive = app.features.auth.confirmDrive;
  window.switchAccount = app.features.auth.switchAccount;
  window.openDriveModal = app.features.auth.openDriveModal;
  window.proceedToValidate = app.features.review.proceedToValidate;
  window.reconnectDrive = app.features.auth.reconnectDrive;
  window.switchUploadTab = app.features.drive.switchUploadTab;
  window.selectLocCard = app.features.drive.selectLocCard;
  window.selectDriveLocCard = app.features.drive.selectDriveLocCard;
  window.handleDriveFolderSelect = app.features.drive.handleDriveFolderSelect;
  window.handleDriveSyncSettingsChange = app.features.drive.handleDriveSyncSettingsChange;
  window.handleDriveDateRangeChange = app.features.drive.handleDriveDateRangeChange;
  window.refreshDriveFolders = app.features.drive.refreshDriveFolders;
  window.syncDriveManualSelectionState = app.features.drive.syncDriveManualSelectionState;
  window.syncDriveCustomSiteState = app.features.drive.syncDriveCustomSiteState;
  window.handleDriveManualSelectionKeydown = app.features.drive.handleDriveManualSelectionKeydown;
  window.applyManualDriveFolderSelection = app.features.drive.applyManualDriveFolderSelection;
  window.handleDriveCustomSiteKeydown = app.features.drive.handleDriveCustomSiteKeydown;
  window.applyDriveCustomSite = app.features.drive.applyDriveCustomSite;
  window.openDriveSiteModal = app.features.drive.openDriveSiteModal;
  window.closeDriveSiteModal = app.features.drive.closeDriveSiteModal;
  window.selectDriveAutoSite = app.features.drive.selectDriveAutoSite;
  window.triggerSync = app.features.drive.triggerSync;
  window.cancelDriveSync = app.features.drive.cancelDriveSync;
  window.clearDriveSync = app.features.drive.clearDriveSync;
  window.cancelManualUpload = app.features.drive.cancelManualUpload;
  window.loadDriveSyncStatus = app.features.drive.loadDriveSyncStatus;
  window.updateSlider = app.features.pipeline.updateSlider;
  window.toggleRunModel = app.features.pipeline.toggleRunModel;
  window.toggleDriveRunModel = app.features.pipeline.toggleDriveRunModel;
  window.cancelPipelineRun = app.features.pipeline.cancelPipelineRun;
  window.toggleRunDetail = app.features.pipeline.toggleRunDetail;
  window.downloadPipelineResult = app.features.pipeline.downloadPipelineResult;
  window.navigateReview = app.features.review.navigateReview;
  window.reviewAction = app.features.review.reviewAction;
  window.askFlagConfirm = app.features.review.askFlagConfirm;
  window.setRFilter = app.features.review.setRFilter;
  window.toggleHumanFilter = app.features.review.toggleHumanFilter;
  window.toggleSort = app.features.review.toggleSort;
  window.toggleBurstView = app.features.review.toggleBurstView;
  window.openSpeciesEdit = app.features.review.openSpeciesEdit;
  window.saveSpeciesEdit = app.features.review.saveSpeciesEdit;
  window.cancelSpeciesEdit = app.features.review.cancelSpeciesEdit;
  window.showSpeciesDropdown = app.features.review.showSpeciesDropdown;
  window.hideSpeciesDropdown = app.features.review.hideSpeciesDropdown;
  window.filterSpeciesOptions = app.features.review.filterSpeciesOptions;
  window.undoLastAction = app.features.review.undoLastAction;
  window.askBurstConfirm = app.features.review.askBurstConfirm;
  window.burstAction = app.features.review.burstAction;
  window.undoBurstAction = app.features.review.undoBurstAction;
  window.onValidatePageEnter = () => app.features.validate.onPageEnter();
  window.toggleAffectedPanel = app.features.validate.toggleAffectedPanel;
  window.updateTimePreview = app.features.validate.updateTimePreview;
  window.updateTimePreviewMulti = () => app.features.validate.updateTimePreviewMulti();
  window.toggleUnprocPanel = app.features.validate.toggleUnprocPanel;
  window.runValidation = app.features.validate.runValidation;
  window.toggleExportOption = app.features.export.toggleExportOption;
  window.toggleExportFilter = app.features.export.toggleExportFilter;
  window.startExport = app.features.export.startExport;
  window.applyExportOptions = app.features.export.applyExportOptions;
  window.closeExportModal = app.features.export.closeExportModal;
  window.confirmExport = app.features.export.confirmExport;
  window.syncExportFilenamePreview = app.features.export.syncExportFilenamePreview;
  window.downloadFile = app.features.export.downloadFile;
  window.previewTimeCorrection = () => app.features.validate.previewTimeCorrection();
  window.filterRunHistoryByDate = function() {
    const fromInput = document.getElementById("run-history-date-from");
    const toInput = document.getElementById("run-history-date-to");
    app.features.pipeline.applyDateFilter({
      from: fromInput?.value || "",
      to: toInput?.value || ""
    });
  };
  
  window.clearRunHistoryFilter = function() {
    app.features.pipeline.applyDateFilter({ from: "", to: "" });
  };
  window.applyTimeCorrection = () => app.features.validate.applyTimeCorrection();
  if (typeof window.__uciNatureFlushDeferred === "function") {
    try { window.__uciNatureFlushDeferred(); } catch (err) { console.error(err); }
  }
}
