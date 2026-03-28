import json
import os
import tempfile
import threading
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "ui" / "backend" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSION_FILE = DATA_DIR / "session.json"
SESSION_LOCK = threading.RLock()

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
        "discovered_count": 0,
        "downloaded_count": 0,
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


def read_session() -> dict:
    with SESSION_LOCK:
        if not SESSION_FILE.exists():
            return deepcopy(DEFAULT_SESSION)

        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return deepcopy(DEFAULT_SESSION)

        return _merge_defaults(data, DEFAULT_SESSION)


def write_session(data: dict) -> None:
    merged = _merge_defaults(data or {}, DEFAULT_SESSION)
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

    with SESSION_LOCK:
        temp_fd, temp_path = tempfile.mkstemp(
            dir=str(SESSION_FILE.parent),
            prefix=f"{SESSION_FILE.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, SESSION_FILE)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
