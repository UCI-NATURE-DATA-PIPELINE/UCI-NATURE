/** DOM helpers used across feature modules and partial loading. */
export function byId(id) {
  return document.getElementById(id);
}

export function setText(id, value) {
  const element = byId(id);
  if (element) {
    element.textContent = value;
  }
}

export function setHTML(id, value) {
  const element = byId(id);
  if (element) {
    element.innerHTML = value;
  }
}

export function setDisplay(id, value) {
  const element = byId(id);
  if (element) {
    element.style.display = value;
  }
}

export function toggleClass(elementOrId, className, enabled) {
  const element = typeof elementOrId === "string" ? byId(elementOrId) : elementOrId;
  if (element) {
    element.classList.toggle(className, enabled);
  }
}

function renderPartialLoadError(url) {
  return `<div style="color:red">Failed to load ${url}</div>`;
}

function normalizePartialReference(url) {
  if (typeof url !== "string") return "";
  const trimmed = url.trim();
  if (!trimmed) return "";
  if (trimmed.startsWith("/")) {
    return `.${trimmed}`;
  }
  return trimmed;
}

function resolvePartialUrl(url, baseUrl = window.location.href) {
  const normalizedUrl = normalizePartialReference(url);
  try {
    return {
      normalizedUrl,
      resolvedUrl: new URL(normalizedUrl, baseUrl).toString()
    };
  } catch (error) {
    console.error(`Failed to resolve partial path: ${normalizedUrl || url}`, error);
    return {
      normalizedUrl,
      resolvedUrl: ""
    };
  }
}

async function fetchPartialMarkup(url) {
  if (!url) {
    return renderPartialLoadError("unknown partial");
  }

  console.log("Loading partial:", url);

  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      console.error(`Failed to load: ${url}`);
      return renderPartialLoadError(url);
    }
    return response.text();
  } catch (error) {
    console.error(`Failed to load: ${url}`, error);
    return renderPartialLoadError(url);
  }
}

export async function loadHtmlPartial(url, baseUrl = window.location.href) {
  const { normalizedUrl, resolvedUrl } = resolvePartialUrl(url, baseUrl);
  console.log("Resolved partial:", resolvedUrl, "->", normalizedUrl);
  const markup = await fetchPartialMarkup(resolvedUrl);
  const template = document.createElement("template");
  template.innerHTML = markup;

  const partialNodes = Array.from(template.content.querySelectorAll("[data-partial]"));
  for (const node of partialNodes) {
    const partialUrl = node.getAttribute("data-partial");
    if (!partialUrl) continue;
    const partialMarkup = await loadHtmlPartial(partialUrl, resolvedUrl);
    const fragment = document.createRange().createContextualFragment(partialMarkup);
    node.replaceWith(fragment);
  }

  return template.innerHTML;
}
