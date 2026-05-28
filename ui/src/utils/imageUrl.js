/** Image URL resolver — same logic the API base uses, but for /images/*.
 *
 * The backend mounts `data/staging` at `/images` (see `ui/backend/main.py`).
 * On AWS the page is served from https://uci-nature-pipeline.duckdns.org
 * and Caddy proxies same-origin `/images/*` to the backend container, so we
 * MUST emit relative URLs. Emitting http://localhost:8000/... breaks AWS
 * with a mixed-content error and points the browser at the user's local
 * machine. On local dev the page is served from http://localhost:5500 and
 * the backend lives at http://localhost:8000, so we need an absolute URL.
 *
 * Rules:
 *   1. If the input is already a relative /images URL → leave it alone.
 *   2. If the input was incorrectly absolutized to a localhost / 127.0.0.1
 *      host → strip the host, keep only the /images path. This lets stale
 *      cached payloads heal automatically.
 *   3. Otherwise, prefix the configured BACKEND_BASE on local dev, leave it
 *      relative on production so Caddy proxies it.
 */
import { BACKEND_BASE } from "../services/core/http.js";

const LOCALHOST_PREFIX_RE = /^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?(?=\/)/i;

function stripLocalhostHost(value) {
  return String(value || "").replace(LOCALHOST_PREFIX_RE, "");
}

function isOnLocalhost() {
  const { hostname } = window.location;
  return hostname === "127.0.0.1" || hostname === "localhost";
}

export function resolveImageUrl(input) {
  const raw = String(input || "").trim();
  if (!raw) return "";

  // Already a relative path? Either it's already correct (/images/...) or
  // someone passed a relative path we should keep. Either way, don't
  // touch the leading slash.
  if (raw.startsWith("/")) {
    return isOnLocalhost() ? `${BACKEND_BASE}${raw}` : raw;
  }

  // Defensive: strip http://localhost(:port) / http://127.0.0.1(:port)
  // prefixes off URLs that the backend or a stale cache produced.
  const stripped = stripLocalhostHost(raw);
  if (stripped !== raw) {
    return isOnLocalhost() ? `${BACKEND_BASE}${stripped}` : stripped;
  }

  // Any other absolute URL (e.g. an external CDN) is passed through.
  return raw;
}
