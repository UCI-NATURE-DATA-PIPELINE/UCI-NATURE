/** Header badge rendering for backend connectivity and pipeline runtime readiness. */
import { appState } from "../../state/appState.js";

export function createBackendStatus() {
  function applyBackendHealthStatus(health = null) {
    const connected = Boolean(health?.connected);
    const runtimeReady = connected && health?.pipeline_runtime_ready !== false;

    appState.backendHealth = {
      connected,
      pipelineRuntimeReady: runtimeReady,
      detail: health?.pipeline_runtime_detail || "",
      checkedAt: new Date().toISOString()
    };

    const badge = document.getElementById("backend-badge");
    const dot = document.getElementById("backend-dot");
    const text = document.getElementById("backend-text");

    if (badge) {
      badge.classList.toggle("online", connected);
      badge.classList.toggle("offline", !connected);
      badge.classList.toggle("warning", connected && !runtimeReady);
    }
    if (dot) {
      dot.classList.toggle("on", connected && runtimeReady);
      dot.classList.toggle("warn", connected && !runtimeReady);
      dot.classList.toggle("off", !connected);
    }
    if (text) {
      if (!connected) text.textContent = "Backend offline";
      else if (!runtimeReady) text.textContent = "Backend connected · pipeline runtime unavailable";
      else text.textContent = "Backend connected";
    }
  }

  return {
    applyBackendHealthStatus
  };
}
