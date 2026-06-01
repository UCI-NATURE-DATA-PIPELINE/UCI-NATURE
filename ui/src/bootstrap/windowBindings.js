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
  
  window.deleteRunHistoryItem = function(runId, btnElement) {
    if (!confirm("Are you sure you want to remove this run from your history?")) return;
    
    const storageKey = "uci_nature_run_history";
    let stored = JSON.parse(localStorage.getItem(storageKey) || "[]");
    stored = stored.filter(run => run.run_id !== runId);
    localStorage.setItem(storageKey, JSON.stringify(stored));
    
    if (btnElement) {
      const row = btnElement.closest('tr');
      if (row) row.remove();
    }
    
    const detailId = String(runId).replace(/[^a-zA-Z0-9_-]/g, "");
    const detailRow = document.getElementById(`rh-detail-${detailId}`);
    if (detailRow) detailRow.remove();
    
    const historyNote = document.getElementById("run-history-note");
    if (historyNote) {
      const count = stored.length;
      if (count > 0) {
        historyNote.textContent = `${count} run${count === 1 ? "" : "s"} stored`;
      } else {
        historyNote.textContent = "Latest backend run";
        const tbody = document.getElementById("run-history-body");
        if (tbody) {
          tbody.innerHTML = '<tr><td colspan="7" style="color:var(--muted);padding:18px 12px">No runs yet. Start a pipeline run from this page to see history here.</td></tr>';
        }
      }
    }
  };

  window.toggleRunSelection = function() {
    const checkboxes = document.querySelectorAll('.run-checkbox');
    const selected = Array.from(checkboxes).filter(cb => cb.checked);
    const count = selected.length;
    
    const countEl = document.getElementById('run-history-selected-count');
    const btnEl = document.getElementById('run-history-delete-btn');
    const selectAllEl = document.getElementById('run-history-select-all');
    
    if (countEl) countEl.textContent = `${count} selected`;
    if (btnEl) btnEl.style.display = count > 0 ? 'inline-flex' : 'none';
    
    if (selectAllEl && checkboxes.length > 0) {
      selectAllEl.checked = (count === checkboxes.length);
    }
  };
  
  window.toggleAllRuns = function(isChecked) {
    const checkboxes = document.querySelectorAll('.run-checkbox');
    checkboxes.forEach(cb => cb.checked = isChecked);
    toggleRunSelection();
  };
  
  window.deleteSelectedRuns = function() {
    const checkboxes = document.querySelectorAll('.run-checkbox');
    const selectedCheckboxes = Array.from(checkboxes).filter(cb => cb.checked);
    const selectedIds = selectedCheckboxes.map(cb => cb.value);
  
    if (selectedIds.length === 0) return;
    if (!confirm(`Are you sure you want to remove ${selectedIds.length} run(s) from your history?`)) return;
  
    const storageKey = "uci_nature_run_history";
    let stored = JSON.parse(localStorage.getItem(storageKey) || "[]");
    stored = stored.filter(run => !selectedIds.includes(String(run.run_id)));
    localStorage.setItem(storageKey, JSON.stringify(stored));
    selectedCheckboxes.forEach(cb => {
      const row = cb.closest('tr');
      if (row) row.remove();
      
      const detailId = String(cb.value).replace(/[^a-zA-Z0-9_-]/g, "");
      const detailRow = document.getElementById(`rh-detail-${detailId}`);
      if (detailRow) detailRow.remove();
    });
    toggleRunSelection();
    const historyNote = document.getElementById("run-history-note");
    if (historyNote) {
      const count = stored.length;
      if (count > 0) {
        historyNote.textContent = `${count} run${count === 1 ? "" : "s"} stored`;
      } else {
        historyNote.textContent = "Latest backend run";
        const tbody = document.getElementById("run-history-body");
        if (tbody) {
          tbody.innerHTML = '<tr><td colspan="8" style="color:var(--muted);padding:18px 12px">No runs yet. Start a pipeline run from this page to see history here.</td></tr>';
        }
      }
    }
  };

  window.clearRunHistoryFilter = function() {
    app.features.pipeline.applyDateFilter({ from: "", to: "" });
  };
  window.applyTimeCorrection = () => app.features.validate.applyTimeCorrection();
  if (typeof window.__uciNatureFlushDeferred === "function") {
    try { window.__uciNatureFlushDeferred(); } catch (err) { console.error(err); }
  }
}
