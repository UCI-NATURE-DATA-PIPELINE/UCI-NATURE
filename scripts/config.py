import os


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _normalize_origin(value: str) -> str:
    return (value or "").strip().rstrip("/")


def _join_origin(origin: str, path: str) -> str:
    origin = _normalize_origin(origin)
    if not origin:
        return ""
    normalized_path = "/" + str(path or "").lstrip("/")
    return f"{origin}{normalized_path}"


APP_ENV = os.getenv("UCI_NATURE_APP_ENV", "local").strip().lower() or "local"

SERVICE_ACCOUNT_FILE = os.getenv(
    "UCI_NATURE_SERVICE_ACCOUNT_FILE",
    "secrets/inf191a-uci-nature-sa.json",
)

FOLDER_ID = os.getenv("UCI_NATURE_FOLDER_ID", "")
OUT_DIR = os.getenv("UCI_NATURE_OUT_DIR", "data/staging")
MAX_DOWNLOADS = _env_int("UCI_NATURE_MAX_DOWNLOADS", 500)

PUBLIC_FRONTEND_ORIGIN = _normalize_origin(
    os.getenv("UCI_NATURE_PUBLIC_FRONTEND_ORIGIN", "")
)
PUBLIC_BACKEND_ORIGIN = _normalize_origin(
    os.getenv("UCI_NATURE_PUBLIC_BACKEND_ORIGIN", "")
) or PUBLIC_FRONTEND_ORIGIN

GOOGLE_OAUTH_CLIENT_ID = os.getenv("UCI_NATURE_GOOGLE_OAUTH_CLIENT_ID", "").strip()
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("UCI_NATURE_GOOGLE_OAUTH_CLIENT_SECRET", "").strip()

GOOGLE_OAUTH_REDIRECT_URI = os.getenv(
    "UCI_NATURE_GOOGLE_OAUTH_REDIRECT_URI",
    _join_origin(PUBLIC_BACKEND_ORIGIN, "/api/auth/google/callback")
    or "http://127.0.0.1:8000/api/auth/google/callback",
).strip()

FRONTEND_SUCCESS_REDIRECT = os.getenv(
    "UCI_NATURE_FRONTEND_SUCCESS_REDIRECT",
    (_join_origin(PUBLIC_FRONTEND_ORIGIN, "/") or "http://127.0.0.1:5500/")
    + "?google_auth=success",
).strip()

PIPELINE_DRIVE_CACHE_POLICY = (
    os.getenv("UCI_NATURE_PIPELINE_DRIVE_CACHE_POLICY", "reuse_if_ready").strip().lower()
    or "reuse_if_ready"
)