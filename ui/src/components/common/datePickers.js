/** Simple static date pickers for the validate and export screens. */
import { appState } from "../../state/appState.js";

export function buildDatePickers() {
  ["start", "end", "export-start", "export-end"].forEach((id) => {
    const popup = document.getElementById(`dp-popup-${id}`);
    if (!popup) {
      return;
    }

    popup.innerHTML = `
      <div class="dp-inner">
        <div class="dp-head">
          <strong>March 2026</strong>
        </div>
        <div class="dp-grid">
          ${Array.from({ length: 30 }, (_, index) => `
            <button type="button" class="dp-day" onclick="pickDate('${id}','Mar ${index + 1}, 2026')">${index + 1}</button>
          `).join("")}
        </div>
      </div>
    `;
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".dp-wrap")) {
      closeAllDatePickers();
    }
  });
}

export function openDP(id) {
  closeAllDatePickers();
  appState.activeDatePicker = id;
  document.getElementById(`dp-popup-${id}`)?.classList.add("open");
}

export function closeAllDatePickers() {
  document.querySelectorAll(".dp-popup").forEach((element) => {
    element.classList.remove("open");
  });
  appState.activeDatePicker = null;
}

export function pickDate(id, value) {
  const input = document.getElementById(`dp-text-${id}`);
  if (input) {
    input.value = value;
  }
  closeAllDatePickers();
}
