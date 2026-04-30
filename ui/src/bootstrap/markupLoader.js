/** App bootstrap helper for loading page and feature HTML partials into the shell. */
import { loadHtmlPartial } from "../utils/dom.js";

const FEATURE_NAMES = ["dashboard", "drive", "pipeline", "review", "validate", "export", "statistics"];
const FEATURES_BASE_URL = new URL("../features/", import.meta.url);
const AUTH_MARKUP_URL = new URL("auth/auth.html", FEATURES_BASE_URL).href;
const FEATURE_PARTIALS = FEATURE_NAMES.map(
  (feature) => new URL(`${feature}/${feature}.html`, FEATURES_BASE_URL).href
);

export async function loadFeatureMarkup() {
  const authRoot = document.getElementById("auth-root");
  const contentRoot = document.getElementById("feature-content");
  if (!authRoot || !contentRoot) return;

  const [authHtml, ...pageHtml] = await Promise.all([
    loadHtmlPartial(AUTH_MARKUP_URL),
    ...FEATURE_PARTIALS.map((partial) => loadHtmlPartial(partial))
  ]);

  authRoot.innerHTML = authHtml;
  contentRoot.innerHTML = pageHtml.join("\n");
}
