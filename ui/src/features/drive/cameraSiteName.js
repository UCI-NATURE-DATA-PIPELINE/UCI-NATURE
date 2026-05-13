const ARCHIVE_EXT_RE = /\.(zip|tar|tgz|tar\.gz)$/i;
const UNSAFE_SITE_RE = /[^A-Za-z0-9._\- ]+/g;

function stripExportNoise(value) {
  let name = String(value || "").trim().replace(ARCHIVE_EXT_RE, "");
  name = name.replace(UNSAFE_SITE_RE, " ");
  name = name.replace(/(?:^|[_\-\s])\d{8}T\d{6}Z(?:$|[_\-\s])/gi, " ");
  name = name.replace(/^[\s_-]*(?:19|20)\d{2}[\s_-]+\d{1,2}[\s_-]+\d{1,2}[\s_-]*/g, "");
  name = name.replace(/[\s_-]+(?:19|20)\d{2}[\s_-]+\d{1,2}(?:[\s_-]+\d{1,2})?[\s_-]*$/g, "");
  name = name.replace(/(?:[\s_-]+\d+){2,}$/g, "");
  return name;
}

function humanizeSiteName(value) {
  return String(value || "")
    .replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/([A-Za-z])(\d+)/g, "$1 $2")
    .replace(/(\d+)([A-Za-z])/g, "$1 $2")
    .replace(/\s+/g, " ")
    .trim();
}

export function normalizeCameraSiteName(value) {
  let name = stripExportNoise(value);
  name = humanizeSiteName(name);
  if (!name) return "";
  return name.slice(0, 64).trim();
}

