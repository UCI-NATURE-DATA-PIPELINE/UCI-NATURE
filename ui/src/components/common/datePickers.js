/** Simple date pickers for the validate and export screens. */
import { appState } from "../../state/appState.js";

const MONTHS = [
  "January","February","March","April","May","June",
  "July","August","September","October","November","December"
];

const dpViewState = {};

function getLinkedMin(id) {
  if (id === "end") {
    const val = document.getElementById("dp-text-start")?.value;
    if (val) { const d = new Date(val); if (!isNaN(d)) return d; }
  }
  return null;
}

function getLinkedMax(id) {
  if (id === "start") {
    const val = document.getElementById("dp-text-end")?.value;
    if (val) { const d = new Date(val); if (!isNaN(d)) return d; }
  }
  return null;
}

function renderDP(id) {
  const popup = document.getElementById(`dp-popup-${id}`);
  if (!popup) return;

  const now = new Date();

  if (!dpViewState[id]) {
    const existing = document.getElementById(`dp-text-${id}`)?.value;
    const init = existing ? new Date(existing) : now;
    dpViewState[id] = {
      year: isNaN(init) ? now.getFullYear() : init.getFullYear(),
      month: isNaN(init) ? now.getMonth() : init.getMonth()
    };
  }

  const { year, month } = dpViewState[id];
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const minDate = getLinkedMin(id);
  const maxDate = getLinkedMax(id);

  const selected = document.getElementById(`dp-text-${id}`)?.value;
  const selDate = selected ? new Date(selected) : null;

  let cells = "";
  for (let i = 0; i < firstDay; i++) {
    cells += `<div style="width:36px;height:36px"></div>`;
  }
  for (let d = 1; d <= daysInMonth; d++) {
    const thisDate = new Date(year, month, d);
    const isSelected = selDate && thisDate.toDateString() === selDate.toDateString();
    const isToday = thisDate.toDateString() === now.toDateString();
    const disabled = (minDate && thisDate < minDate) || (maxDate && thisDate > maxDate);
    const label = `${MONTHS[month].slice(0, 3)} ${d}, ${year}`;

    const bg = isSelected ? "#2B6CB0" : "transparent";
    const color = isSelected ? "#fff" : disabled ? "#CBD5E0" : isToday ? "#2B6CB0" : "#2D3748";
    const border = isToday && !isSelected ? "1px solid #2B6CB0" : "1px solid transparent";
    const cursor = disabled ? "not-allowed" : "pointer";

    cells += `<button type="button"
      onclick="event.stopPropagation();${disabled ? "" : `pickDate('${id}','${label}')`}"
      ${disabled ? "disabled" : ""}
      style="width:36px;height:36px;border-radius:50%;background:${bg};color:${color};border:${border};cursor:${cursor};font-size:13px;font-weight:${isSelected ? "600" : "400"}"
    >${d}</button>`;
  }

  popup.innerHTML = `
    <div style="background:#fff;border:1px solid #E2E8F0;border-radius:10px;box-shadow:0 4px 20px rgba(0,0,0,0.12);padding:16px;width:280px;user-select:none">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <button type="button"
          onclick="event.stopPropagation();dpNav('${id}',-1)"
          style="width:32px;height:32px;border-radius:6px;border:1px solid #E2E8F0;background:#F7FAFC;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center;color:#4A5568"
        >◀</button>
        <strong style="font-size:14px;color:#2D3748">${MONTHS[month]} ${year}</strong>
        <button type="button"
          onclick="event.stopPropagation();dpNav('${id}',1)"
          style="width:32px;height:32px;border-radius:6px;border:1px solid #E2E8F0;background:#F7FAFC;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center;color:#4A5568"
        >▶</button>
      </div>
      <div style="display:grid;grid-template-columns:repeat(7,36px);gap:2px;margin-bottom:4px">
        ${["Su","Mo","Tu","We","Th","Fr","Sa"].map(d =>
          `<div style="width:36px;text-align:center;font-size:11px;font-weight:600;color:#A0AEC0;padding-bottom:4px">${d}</div>`
        ).join("")}
      </div>
      <div style="display:grid;grid-template-columns:repeat(7,36px);gap:2px">
        ${cells}
      </div>
    </div>
  `;
}

export function buildDatePickers() {
  ["start", "end"].forEach((id) => {
    if (!document.getElementById(`dp-popup-${id}`)) return;
    renderDP(id);
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".dp-wrap")) closeAllDatePickers();
  });
}

export function dpNav(id, dir) {
  if (!dpViewState[id]) {
    dpViewState[id] = { year: new Date().getFullYear(), month: new Date().getMonth() };
  }
  dpViewState[id].month += dir;
  if (dpViewState[id].month > 11) { dpViewState[id].month = 0; dpViewState[id].year++; }
  if (dpViewState[id].month < 0)  { dpViewState[id].month = 11; dpViewState[id].year--; }
  renderDP(id);
  document.getElementById(`dp-popup-${id}`)?.classList.add("open");
}

export function openDP(id) {
  closeAllDatePickers();
  appState.activeDatePicker = id;
  renderDP(id);
  document.getElementById(`dp-popup-${id}`)?.classList.add("open");
}

export function closeAllDatePickers() {
  document.querySelectorAll(".dp-popup").forEach((el) => el.classList.remove("open"));
  appState.activeDatePicker = null;
}

export function pickDate(id, value) {
  const input = document.getElementById(`dp-text-${id}`);
  if (input) input.value = value;
  closeAllDatePickers();
  if (id === "start") { delete dpViewState["end"]; renderDP("end"); }
  if (id === "end") { delete dpViewState["start"]; renderDP("start"); }
  if (typeof window.onDeploymentDateChange === "function") window.onDeploymentDateChange();
}