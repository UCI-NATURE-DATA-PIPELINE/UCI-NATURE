/** Runtime flags for browser-native local development and deployed environments. */
const LOCAL_DEV_HOSTS = new Set(["127.0.0.1", "localhost"]);

function parseBooleanFlag(value) {
  if (typeof value === "boolean") return value;
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return null;
  if (["1", "true", "yes", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "off"].includes(normalized)) return false;
  return null;
}

const configuredDevMode = parseBooleanFlag(
  window.__UCI_NATURE_CONFIG__?.devMode ||
  document.querySelector('meta[name="uci-nature-dev-mode"]')?.content
);

export const DEV_MODE = configuredDevMode ?? LOCAL_DEV_HOSTS.has(window.location.hostname);

export const DEV_USER = Object.freeze({
  name: "Local Dev User",
  email: "dev@local"
});
