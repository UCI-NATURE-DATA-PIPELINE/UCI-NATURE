import json
import os
import re
import secrets
import tempfile
import threading
from copy import deepcopy
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "ui" / "backend" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR = DATA_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
LEGACY_SESSION_FILE = DATA_DIR / "session.json"
SESSION_LOCK = threading.RLock()
SESSION_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,}$")

DEFAULT_SESSION = {
    "token": None,
    "user": None,
    "drive_connected": False,
    "drive_name": None,
    "drive_email": None,
    "selected_drive_folder": None,
    "drive_sync": {
        "status": "idle",
        "source_ready": False,
        "started_at": None,
        "finished_at": None,
        "folder": None,
        "available_count": 0,
        "discovered_count": 0,
        "downloaded_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "discovery_complete": False,
        "cancellation_requested": False,
        "requested_total": 0,
        "images_per_second": None,
        "eta_seconds": None,
        "elapsed_seconds": None,
        "current_file": None,
        "staging_dir": None,
        "drive_index_path": None,
        "error": None,
        "last_sync_message": None,
    },
    "google_auth": {
        "authenticated": False,
        "user": None,
        "access_token": None,
        "refresh_token": None,
        "expires_at": None,
        "oauth_state": None,
    },
}


def _merge_defaults(existing: dict, defaults: dict) -> dict:
    result = deepcopy(defaults)
    for key, value in (existing or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_defaults(value, result[key])
        else:
            result[key] = value
    return result


def _session_file(session_key: str) -> Path:
    normalized = str(session_key or "").strip()
    if not SESSION_KEY_PATTERN.match(normalized):
        raise ValueError("Invalid session key")
    return SESSIONS_DIR / f"{normalized}.json"


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def iter_session_keys() -> list[str]:
    with SESSION_LOCK:
        if not SESSIONS_DIR.exists():
            return []
        return sorted(
            path.stem
            for path in SESSIONS_DIR.glob("*.json")
            if path.is_file() and SESSION_KEY_PATTERN.match(path.stem)
        )


def find_session_key_by_google_oauth_state(oauth_state: Optional[str]) -> Optional[str]:
    normalized_state = str(oauth_state or "").strip()
    if not normalized_state:
        return None

    with SESSION_LOCK:
        for session_key in iter_session_keys():
            session_path = _session_file(session_key)
            try:
                with open(session_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            if ((data.get("google_auth") or {}).get("oauth_state") or "").strip() == normalized_state:
                return session_key

    return None


def read_session(session_key: Optional[str] = None) -> dict:
    session_path = LEGACY_SESSION_FILE
    if session_key:
        try:
            session_path = _session_file(session_key)
        except ValueError:
            return deepcopy(DEFAULT_SESSION)

    with SESSION_LOCK:
        if not session_path.exists():
            return deepcopy(DEFAULT_SESSION)

        try:
            with open(session_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return deepcopy(DEFAULT_SESSION)

        return _merge_defaults(data, DEFAULT_SESSION)


def write_session(data: dict, session_key: Optional[str] = None) -> None:
    merged = _merge_defaults(data or {}, DEFAULT_SESSION)
    session_path = LEGACY_SESSION_FILE if not session_key else _session_file(session_key)
    session_path.parent.mkdir(parents=True, exist_ok=True)

    with SESSION_LOCK:
        temp_fd, temp_path = tempfile.mkstemp(
            dir=str(session_path.parent),
            prefix=f"{session_path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, session_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
