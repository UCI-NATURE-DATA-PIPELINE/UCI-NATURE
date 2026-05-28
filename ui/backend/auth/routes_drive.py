from copy import deepcopy
from datetime import datetime
import re
import threading
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ui.backend.auth.routes import get_google_auth_state
from ui.backend.cancellation import CancellationToken, OperationCancelled
from ui.backend.services.drive_staging_service import stage_selected_drive_folder
from ui.backend.services.pipeline_service import resolve_pipeline_staging_dir
from ui.backend.session_store import read_session, write_session

router = APIRouter(prefix="/api/drive", tags=["drive"])
GOOGLE_DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_REQUEST_TIMEOUT_SECONDS = 10
DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
DRIVE_SHORTCUT_MIME_TYPE = "application/vnd.google-apps.shortcut"
DRIVE_FOLDER_LIST_PAGE_SIZE = 100
_UNSET = object()
DEFAULT_DRIVE_SYNC_STATE = {
    "status": "idle",
    "source_ready": False,
    "started_at": None,
    "finished_at": None,
    "folder": None,
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
}
DRIVE_SYNC_LOCK = threading.RLock()
DRIVE_SYNC_STATES: Dict[str, Dict[str, Any]] = {}
DRIVE_SYNC_CANCEL_TOKENS: Dict[str, CancellationToken] = {}


class SelectFolderRequest(BaseModel):
    folder_id: str
    folder_name: Optional[str] = None
    camera_location: Optional[str] = None
    max_files: Optional[int] = None


class SyncFolderRequest(BaseModel):
    max_files: Optional[int] = None


def _require_auth_session(authorization: Optional[str]) -> Tuple[str, Dict[str, Any]]:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    session_token = authorization.replace("Bearer ", "", 1).strip()
    session = read_session(session_token)
    if not session.get("token") or session["token"] != session_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    return session_token, session


def _normalize_sync_limit(value: Optional[int]) -> Optional[int]:
    if value in (None, 0):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Sync limit must be a whole number") from exc

    if normalized < 0:
        raise HTTPException(status_code=400, detail="Sync limit cannot be negative")
    return normalized or None


def _normalize_camera_location(value: Optional[str]) -> Optional[str]:
    normalized = re.sub(r"\.(zip|tar|tgz|tar\.gz)$", "", str(value or "").strip(), flags=re.IGNORECASE)
    normalized = re.sub(r"[^A-Za-z0-9._\- ]+", " ", normalized)
    normalized = re.sub(r"(?:^|[_\-\s])\d{8}T\d{6}Z(?:$|[_\-\s])", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^[\s_-]*(?:19|20)\d{2}[\s_-]+\d{1,2}[\s_-]+\d{1,2}[\s_-]*", "", normalized)
    normalized = re.sub(r"[\s_-]+(?:19|20)\d{2}[\s_-]+\d{1,2}(?:[\s_-]+\d{1,2})?[\s_-]*$", "", normalized)
    normalized = re.sub(r"(?:[\s_-]+\d+){2,}$", "", normalized)
    normalized = re.sub(r"[_-]+", " ", normalized)
    normalized = re.sub(r"([a-z])([A-Z])", r"\1 \2", normalized)
    normalized = re.sub(r"([A-Za-z])(\d+)", r"\1 \2", normalized)
    normalized = re.sub(r"(\d+)([A-Za-z])", r"\1 \2", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()[:64]
    return normalized or None


def _fresh_drive_sync_state(folder: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = deepcopy(DEFAULT_DRIVE_SYNC_STATE)
    if folder:
        state["folder"] = {
            "id": folder.get("id"),
            "name": folder.get("name"),
        }
    return state


def _set_active_drive_sync_state(session_key: str, state: Dict[str, Any]) -> None:
    with DRIVE_SYNC_LOCK:
        DRIVE_SYNC_STATES[session_key] = deepcopy(state)


def _update_active_drive_sync_state(session_key: str, **updates: Any) -> None:
    with DRIVE_SYNC_LOCK:
        active_state = DRIVE_SYNC_STATES.setdefault(
            session_key,
            deepcopy(DEFAULT_DRIVE_SYNC_STATE),
        )
        active_state.update(updates)


def _read_active_drive_sync_state(session_key: str) -> Dict[str, Any]:
    with DRIVE_SYNC_LOCK:
        return deepcopy(DRIVE_SYNC_STATES.get(session_key) or DEFAULT_DRIVE_SYNC_STATE)


def _create_drive_sync_cancel_token(session_key: str) -> CancellationToken:
    token = CancellationToken()
    with DRIVE_SYNC_LOCK:
        DRIVE_SYNC_CANCEL_TOKENS[session_key] = token
    return token


def get_drive_sync_cancel_token(session_key: str) -> Optional[CancellationToken]:
    with DRIVE_SYNC_LOCK:
        return DRIVE_SYNC_CANCEL_TOKENS.get(session_key)


def _clear_drive_sync_cancel_token(session_key: str) -> None:
    with DRIVE_SYNC_LOCK:
        DRIVE_SYNC_CANCEL_TOKENS.pop(session_key, None)


def _build_persisted_drive_sync_state(
    *,
    base: Optional[Dict[str, Any]] = None,
    folder: Any = _UNSET,
    status: Any = _UNSET,
    source_ready: Any = _UNSET,
    started_at: Any = _UNSET,
    finished_at: Any = _UNSET,
    discovered_count: Any = _UNSET,
    downloaded_count: Any = _UNSET,
    current_file: Any = _UNSET,
    discovery_complete: Any = _UNSET,
    cancellation_requested: Any = _UNSET,
    staging_dir: Any = _UNSET,
    drive_index_path: Any = _UNSET,
    error: Any = _UNSET,
    last_sync_message: Any = _UNSET,
) -> Dict[str, Any]:
    state = _fresh_drive_sync_state(folder=None if folder is _UNSET else folder)

    if base:
        state.update({
            "status": base.get("status", state["status"]),
            "source_ready": bool(base.get("source_ready", state["source_ready"])),
            "started_at": base.get("started_at"),
            "finished_at": base.get("finished_at"),
            "folder": base.get("folder") or state["folder"],
            "discovered_count": int(base.get("discovered_count") or 0),
            "downloaded_count": int(base.get("downloaded_count") or 0),
            "failed_count": int(base.get("failed_count") or 0),
            "skipped_count": int(base.get("skipped_count") or 0),
            "discovery_complete": bool(base.get("discovery_complete", state["discovery_complete"])),
            "cancellation_requested": bool(base.get("cancellation_requested", state["cancellation_requested"])),
            "requested_total": int(base.get("requested_total") or 0),
            "images_per_second": base.get("images_per_second"),
            "eta_seconds": base.get("eta_seconds"),
            "elapsed_seconds": base.get("elapsed_seconds"),
            "current_file": base.get("current_file"),
            "staging_dir": base.get("staging_dir"),
            "drive_index_path": base.get("drive_index_path"),
            "error": base.get("error"),
            "last_sync_message": base.get("last_sync_message"),
        })

    if folder is not _UNSET:
        state["folder"] = {
            "id": folder.get("id") if folder else None,
            "name": folder.get("name") if folder else None,
        }
    if status is not _UNSET:
        state["status"] = status
    if source_ready is not _UNSET:
        state["source_ready"] = bool(source_ready)
    if started_at is not _UNSET:
        state["started_at"] = started_at
    if finished_at is not _UNSET:
        state["finished_at"] = finished_at
    if discovered_count is not _UNSET:
        state["discovered_count"] = int(discovered_count)
    if downloaded_count is not _UNSET:
        state["downloaded_count"] = int(downloaded_count)
    if current_file is not _UNSET:
        state["current_file"] = current_file
    if discovery_complete is not _UNSET:
        state["discovery_complete"] = bool(discovery_complete)
    if cancellation_requested is not _UNSET:
        state["cancellation_requested"] = bool(cancellation_requested)
    if staging_dir is not _UNSET:
        state["staging_dir"] = staging_dir
    if drive_index_path is not _UNSET:
        state["drive_index_path"] = drive_index_path
    if error is not _UNSET:
        state["error"] = error
    if last_sync_message is not _UNSET:
        state["last_sync_message"] = last_sync_message

    return state


def _persist_drive_sync_state(
    session: Dict[str, Any],
    session_key: str,
    state: Dict[str, Any],
) -> None:
    session["drive_sync"] = _build_persisted_drive_sync_state(base=state)
    write_session(session, session_key)


def reset_drive_sync_state(
    session: Dict[str, Any],
    session_key: str,
    *,
    folder: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
) -> Dict[str, Any]:
    state = _build_persisted_drive_sync_state(
        folder=folder,
        status="idle",
        source_ready=False,
        started_at=None,
        finished_at=None,
        discovered_count=0,
        downloaded_count=0,
        current_file=None,
        discovery_complete=False,
        cancellation_requested=False,
        staging_dir=None,
        drive_index_path=None,
        error=None,
        last_sync_message=message,
    )
    _set_active_drive_sync_state(session_key, state)
    _clear_drive_sync_cancel_token(session_key)
    _persist_drive_sync_state(session, session_key, state)
    return state


def start_drive_sync_operation(
    session: Dict[str, Any],
    session_key: str,
    *,
    folder: Dict[str, Any],
    message: str,
    staging_dir: Optional[str] = None,
    requested_total: int = 0,
) -> Dict[str, Any]:
    state = _build_persisted_drive_sync_state(
        folder=folder,
        status="syncing",
        source_ready=False,
        started_at=datetime.now().isoformat(timespec="seconds"),
        finished_at=None,
        discovered_count=0,
        downloaded_count=0,
        current_file=None,
        discovery_complete=False,
        cancellation_requested=False,
        staging_dir=staging_dir,
        drive_index_path=None,
        error=None,
        last_sync_message=message,
    )
    state["requested_total"] = max(0, int(requested_total or 0))
    _create_drive_sync_cancel_token(session_key)
    _set_active_drive_sync_state(session_key, state)
    _persist_drive_sync_state(session, session_key, state)
    return state


def update_drive_sync_progress(
    session_key: str,
    *,
    folder: Dict[str, Any],
    discovered_count: int,
    downloaded_count: int,
    current_file: Optional[str],
    staging_dir: Optional[str],
    message: str,
    failed_count: Optional[int] = None,
    skipped_count: Optional[int] = None,
    discovery_complete: Optional[bool] = None,
    requested_total: Optional[int] = None,
    images_per_second: Optional[float] = None,
    eta_seconds: Optional[float] = None,
    elapsed_seconds: Optional[float] = None,
) -> None:
    updates: Dict[str, Any] = dict(
        folder={
            "id": folder.get("id"),
            "name": folder.get("name"),
        },
        discovered_count=int(discovered_count or 0),
        downloaded_count=int(downloaded_count or 0),
        current_file=current_file,
        staging_dir=staging_dir,
        last_sync_message=message,
    )
    if failed_count is not None:
        updates["failed_count"] = int(failed_count or 0)
    if skipped_count is not None:
        updates["skipped_count"] = int(skipped_count or 0)
    if discovery_complete is not None:
        updates["discovery_complete"] = bool(discovery_complete)
    if requested_total is not None:
        updates["requested_total"] = max(0, int(requested_total or 0))
    if images_per_second is not None:
        updates["images_per_second"] = float(images_per_second or 0.0)
    if eta_seconds is not None:
        updates["eta_seconds"] = float(eta_seconds)
    if elapsed_seconds is not None:
        updates["elapsed_seconds"] = float(elapsed_seconds)
    _update_active_drive_sync_state(session_key, **updates)


def complete_drive_sync_operation(
    session: Dict[str, Any],
    session_key: str,
    *,
    folder: Dict[str, Any],
    sync_result: Dict[str, Any],
    message: str,
) -> Dict[str, Any]:
    completed_state = _build_persisted_drive_sync_state(
        base=_read_active_drive_sync_state(session_key),
        folder=folder,
        status="completed",
        source_ready=True,
        finished_at=datetime.now().isoformat(timespec="seconds"),
        discovered_count=int(sync_result.get("discovered_count") or 0),
        downloaded_count=int(sync_result.get("downloaded_count") or 0),
        current_file=None,
        discovery_complete=True,
        cancellation_requested=False,
        staging_dir=sync_result.get("staging_dir"),
        drive_index_path=sync_result.get("drive_index_path"),
        error=None,
        last_sync_message=message,
    )
    # Carry through performance metrics the sync service produced so the UI
    # sees the final img/sec + elapsed when the run finishes.
    completed_state["failed_count"] = int(sync_result.get("failed_count") or 0)
    completed_state["skipped_count"] = int(sync_result.get("already_staged_count") or 0)
    if sync_result.get("images_per_second") is not None:
        completed_state["images_per_second"] = float(sync_result.get("images_per_second") or 0)
    if sync_result.get("elapsed_seconds") is not None:
        completed_state["elapsed_seconds"] = float(sync_result.get("elapsed_seconds") or 0)
    completed_state["eta_seconds"] = 0.0
    _set_active_drive_sync_state(session_key, completed_state)
    _clear_drive_sync_cancel_token(session_key)
    _persist_drive_sync_state(session, session_key, completed_state)
    return completed_state


def fail_drive_sync_operation(
    session: Dict[str, Any],
    session_key: str,
    *,
    folder: Dict[str, Any],
    error: str,
    message: str = "Drive sync failed",
) -> Dict[str, Any]:
    failed_state = _build_persisted_drive_sync_state(
        base=_read_active_drive_sync_state(session_key),
        folder=folder,
        status="failed",
        source_ready=False,
        finished_at=datetime.now().isoformat(timespec="seconds"),
        cancellation_requested=False,
        error=error,
        last_sync_message=message,
    )
    _set_active_drive_sync_state(session_key, failed_state)
    _clear_drive_sync_cancel_token(session_key)
    _persist_drive_sync_state(session, session_key, failed_state)
    return failed_state


def cancel_drive_sync_operation(
    session: Dict[str, Any],
    session_key: str,
    *,
    folder: Optional[Dict[str, Any]] = None,
    message: str = "Drive sync stopped",
) -> Dict[str, Any]:
    token = get_drive_sync_cancel_token(session_key)
    if token:
        token.cancel()

    selected_folder = folder or session.get("selected_drive_folder") or {}
    cancelled_state = _build_persisted_drive_sync_state(
        base=_read_active_drive_sync_state(session_key),
        folder=selected_folder,
        status="cancelled",
        source_ready=False,
        finished_at=datetime.now().isoformat(timespec="seconds"),
        current_file=None,
        cancellation_requested=True,
        error=None,
        last_sync_message=message,
    )
    _set_active_drive_sync_state(session_key, cancelled_state)
    _persist_drive_sync_state(session, session_key, cancelled_state)
    return cancelled_state


def serialize_drive_sync_state(
    session: Optional[Dict[str, Any]] = None,
    *,
    session_key: Optional[str] = None,
) -> Dict[str, Any]:
    session = session or read_session(session_key)
    selected_folder = session.get("selected_drive_folder")
    persisted_state = _build_persisted_drive_sync_state(
        base=session.get("drive_sync") or {},
        folder=(session.get("drive_sync") or {}).get("folder") or selected_folder,
    )
    active_state = _read_active_drive_sync_state(session_key or "")

    if (
        persisted_state.get("status") == "syncing"
        and active_state.get("status") != "syncing"
    ):
        persisted_state = _build_persisted_drive_sync_state(
            base=persisted_state,
            folder=persisted_state.get("folder") or selected_folder,
            status="failed",
            source_ready=False,
            finished_at=datetime.now().isoformat(timespec="seconds"),
            error=(
                persisted_state.get("error")
                or "The previous Drive sync was interrupted before completion. Start a new sync or run the pipeline again."
            ),
            last_sync_message="Drive sync was interrupted before completion",
        )
        session["drive_sync"] = persisted_state
        write_session(session, session_key)

    state = active_state if active_state.get("status") == "syncing" else persisted_state
    folder = state.get("folder") or selected_folder
    selected_folder_matches = bool(
        folder and selected_folder and folder.get("id") == selected_folder.get("id")
    )
    discovered_count = int(state.get("discovered_count") or 0)
    downloaded_count = int(state.get("downloaded_count") or 0)
    discovery_complete = bool(state.get("discovery_complete") or state.get("status") == "completed")
    requested_total = int(state.get("requested_total") or 0)

    # Progress denominator rules:
    #   1. Discovery done            → downloaded / discovered  (real ratio)
    #   2. Discovery in progress
    #         AND requested_total>0  → downloaded / requested_total
    #                                   (so a 5,000-cap sync doesn't jump to
    #                                    98% just because we've only listed
    #                                    2,294 images so far)
    #   3. Discovery in progress
    #         AND no limit           → 0  (indeterminate; the UI shows
    #                                      "Discovering and downloading...")
    if discovery_complete and discovered_count > 0:
        progress_percent = round((downloaded_count / discovered_count) * 100)
    elif state.get("status") == "completed":
        progress_percent = 100
    elif not discovery_complete and requested_total > 0:
        progress_percent = round((downloaded_count / requested_total) * 100)
    else:
        progress_percent = 0

    # Remaining: prefer requested target during discovery, real total after.
    if discovery_complete:
        remaining_count = max(discovered_count - downloaded_count, 0)
    elif requested_total > 0:
        remaining_count = max(requested_total - downloaded_count, 0)
    else:
        remaining_count = max(discovered_count - downloaded_count, 0)

    failed_count = int(state.get("failed_count") or 0)
    images_per_second = state.get("images_per_second")
    eta_seconds = state.get("eta_seconds")
    elapsed_seconds = state.get("elapsed_seconds")

    return {
        "status": state.get("status") or "idle",
        "source_ready": bool(state.get("source_ready") and selected_folder_matches),
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
        "folder": folder,
        "selected_folder": selected_folder,
        "selected_folder_matches": selected_folder_matches,
        "discovered_count": discovered_count,
        "downloaded_count": downloaded_count,
        "remaining_count": remaining_count,
        "failed_count": failed_count,
        "skipped_count": int(state.get("skipped_count") or 0),
        "discovery_complete": discovery_complete,
        "cancellation_requested": bool(state.get("cancellation_requested")),
        "requested_total": requested_total,
        "images_per_second": (
            float(images_per_second) if images_per_second is not None else None
        ),
        "eta_seconds": float(eta_seconds) if eta_seconds is not None else None,
        "elapsed_seconds": (
            float(elapsed_seconds) if elapsed_seconds is not None else None
        ),
        "progress_percent": progress_percent,
        "current_file": state.get("current_file"),
        "staging_dir": state.get("staging_dir"),
        "drive_index_path": state.get("drive_index_path"),
        "error": state.get("error"),
        "last_sync_message": state.get("last_sync_message"),
    }


def normalize_folder_id(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="Folder ID is required")

    if "drive.google.com" in value and "/folders/" in value:
        value = value.split("/folders/", 1)[1].split("?", 1)[0].split("/", 1)[0]

    return value


def get_google_drive_auth_session(
    authorization: Optional[str],
) -> Tuple[str, Dict[str, Any], Dict[str, Any], str]:
    session_key, session = _require_auth_session(authorization)
    google_auth = get_google_auth_state(session=session, session_key=session_key)
    access_token = google_auth.get("access_token")

    if not google_auth.get("authenticated") or not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated with Google")

    return session_key, session, google_auth, access_token


def invalidate_google_auth_session(session_key: str, session: Dict[str, Any]) -> None:
    google_auth = session.get("google_auth") or {}
    session["google_auth"] = {
        "authenticated": False,
        "user": google_auth.get("user"),
        "access_token": None,
        "refresh_token": google_auth.get("refresh_token"),
        "expires_at": google_auth.get("expires_at"),
        "oauth_state": google_auth.get("oauth_state"),
    }
    session["drive_connected"] = False
    write_session(session, session_key)


def get_google_error_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or "Google Drive API request failed"

    error = payload.get("error")
    if isinstance(error, dict):
        message = (error.get("message") or "").strip()
        if message:
            return message
    if isinstance(error, str) and error.strip():
        return error.strip()

    return response.text.strip() or "Google Drive API request failed"


def drive_api_get(
    *,
    session_key: str,
    session: Dict[str, Any],
    access_token: str,
    path: str = "",
    params: Optional[Dict[str, Union[str, int]]] = None,
    action: str,
) -> Dict[str, Any]:
    url = GOOGLE_DRIVE_FILES_URL if not path else f"{GOOGLE_DRIVE_FILES_URL}/{path}"

    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=DRIVE_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.Timeout as exc:
        raise HTTPException(
            status_code=504,
            detail=f"Google Drive request timed out while trying to {action}",
        ) from exc
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to reach Google Drive while trying to {action}: {exc}",
        ) from exc

    if response.status_code == 401:
        invalidate_google_auth_session(session_key, session)
        raise HTTPException(
            status_code=401,
            detail="Google OAuth session expired or is invalid. Sign in with Google again.",
        )

    if not response.ok:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Failed to {action}: {get_google_error_detail(response)}",
        )

    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Google Drive returned invalid JSON while trying to {action}",
        ) from exc


def _build_drive_folder_list_params(
    *,
    query: str,
    include_shortcut_details: bool = False,
) -> Dict[str, Union[str, int]]:
    fields = "files(id, name, driveId, webViewLink)"
    if include_shortcut_details:
        fields = "files(id, name, driveId, webViewLink, shortcutDetails(targetId, targetMimeType))"

    return {
        "q": query,
        "fields": fields,
        "pageSize": DRIVE_FOLDER_LIST_PAGE_SIZE,
        "orderBy": "name",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
        "corpora": "user",
    }


def _collect_drive_folder_options(
    *,
    session_key: str,
    session: Dict[str, Any],
    access_token: str,
) -> List[Dict[str, Any]]:
    my_drive_results = drive_api_get(
        session_key=session_key,
        session=session,
        access_token=access_token,
        params=_build_drive_folder_list_params(
            query=(
                f"mimeType='{DRIVE_FOLDER_MIME_TYPE}' "
                "and trashed=false "
                "and 'root' in parents"
            ),
        ),
        action="list top-level My Drive folders",
    )
    shared_results = drive_api_get(
        session_key=session_key,
        session=session,
        access_token=access_token,
        params=_build_drive_folder_list_params(
            query=(
                f"mimeType='{DRIVE_FOLDER_MIME_TYPE}' "
                "and trashed=false "
                "and sharedWithMe=true"
            ),
        ),
        action="list shared Google Drive folders",
    )
    shortcut_results = drive_api_get(
        session_key=session_key,
        session=session,
        access_token=access_token,
        params=_build_drive_folder_list_params(
            query=(
                f"mimeType='{DRIVE_SHORTCUT_MIME_TYPE}' "
                "and trashed=false "
                "and 'root' in parents"
            ),
            include_shortcut_details=True,
        ),
        action="list top-level Google Drive shortcuts",
    )

    folders_by_id: Dict[str, Dict[str, Any]] = {}

    def upsert_folder(
        *,
        folder_id: Optional[str],
        name: Optional[str],
        drive_id: Optional[str],
        web_view_link: Optional[str],
        source: str,
        rank: int,
    ) -> None:
        normalized_id = (folder_id or "").strip()
        normalized_name = (name or "").strip()
        if not normalized_id or not normalized_name:
            return

        existing = folders_by_id.get(normalized_id)
        if existing and existing["_rank"] <= rank:
            return

        folders_by_id[normalized_id] = {
            "id": normalized_id,
            "name": normalized_name,
            "drive_id": drive_id,
            "web_view_link": web_view_link,
            "source": source,
            "_rank": rank,
        }

    for folder in my_drive_results.get("files", []):
        upsert_folder(
            folder_id=folder.get("id"),
            name=folder.get("name"),
            drive_id=folder.get("driveId"),
            web_view_link=folder.get("webViewLink"),
            source="my_drive",
            rank=0,
        )

    for folder in shared_results.get("files", []):
        upsert_folder(
            folder_id=folder.get("id"),
            name=folder.get("name"),
            drive_id=folder.get("driveId"),
            web_view_link=folder.get("webViewLink"),
            source="shared",
            rank=1,
        )

    for shortcut in shortcut_results.get("files", []):
        details = shortcut.get("shortcutDetails") or {}
        if details.get("targetMimeType") != DRIVE_FOLDER_MIME_TYPE:
            continue
        upsert_folder(
            folder_id=details.get("targetId"),
            name=shortcut.get("name"),
            drive_id=shortcut.get("driveId"),
            web_view_link=shortcut.get("webViewLink"),
            source="shortcut",
            rank=2,
        )

    normalized_folders = [
        {
            "id": folder["id"],
            "name": folder["name"],
            "drive_id": folder.get("drive_id"),
            "web_view_link": folder.get("web_view_link"),
            "source": folder.get("source"),
        }
        for folder in folders_by_id.values()
    ]

    return sorted(
        normalized_folders,
        key=lambda folder: (str(folder.get("name") or "").lower(), str(folder.get("id") or "")),
    )


@router.get("/folders")
def list_drive_folders(authorization: Optional[str] = Header(default=None)):
    try:
        session_key, session, _, access_token = get_google_drive_auth_session(authorization)
        normalized_folders = _collect_drive_folder_options(
            session_key=session_key,
            session=session,
            access_token=access_token,
        )

        return {
            "folders": normalized_folders,
            "selected_folder": session.get("selected_drive_folder"),
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list Drive folders: {exc}",
        ) from exc


@router.post("/select-folder")
def select_drive_folder(
    payload: SelectFolderRequest,
    authorization: Optional[str] = Header(default=None),
):
    folder_id = normalize_folder_id(payload.folder_id)
    session_key, existing_session = _require_auth_session(authorization)
    current_sync = serialize_drive_sync_state(session=existing_session, session_key=session_key)

    if current_sync["status"] == "syncing":
        raise HTTPException(
            status_code=409,
            detail="A Drive sync is already in progress. Wait for it to finish before changing folders.",
        )

    try:
        _, session, _, access_token = get_google_drive_auth_session(authorization)
        folder = drive_api_get(
            session_key=session_key,
            session=session,
            access_token=access_token,
            path=folder_id,
            params={
                "fields": (
                    "id, name, mimeType, driveId, webViewLink, "
                    "shortcutDetails(targetId,targetMimeType)"
                ),
                "supportsAllDrives": "true",
            },
            action="load the selected Google Drive folder",
        )
    except HTTPException as exc:
        if exc.status_code in (403, 404):
            raise HTTPException(
                status_code=404,
                detail="Drive folder not found or not accessible for the authenticated user",
            ) from exc
        raise

    folder_mime_type = folder.get("mimeType")
    shortcut_details = folder.get("shortcutDetails") or {}
    if not isinstance(shortcut_details, dict):
        shortcut_details = {}
    is_folder = folder_mime_type == DRIVE_FOLDER_MIME_TYPE
    is_folder_shortcut = bool(
        folder_mime_type == DRIVE_SHORTCUT_MIME_TYPE
        and shortcut_details.get("targetMimeType") == DRIVE_FOLDER_MIME_TYPE
        and shortcut_details.get("targetId")
    )
    if not is_folder and not is_folder_shortcut:
        raise HTTPException(status_code=400, detail="Selected file is not a Google Drive folder")

    selected_folder = {
        "id": folder["id"],
        "name": folder["name"],
        "drive_id": folder.get("driveId"),
        "web_view_link": folder.get("webViewLink"),
        "mime_type": folder_mime_type,
        "shortcut_target_id": shortcut_details.get("targetId") if is_folder_shortcut else None,
        "camera_location": _normalize_camera_location(payload.camera_location),
        "max_files": _normalize_sync_limit(payload.max_files),
    }

    previous_folder = existing_session.get("selected_drive_folder") or session.get("selected_drive_folder")
    session["selected_drive_folder"] = selected_folder
    folder_changed = not previous_folder or previous_folder.get("id") != selected_folder["id"]
    settings_changed = (
        _normalize_camera_location((previous_folder or {}).get("camera_location"))
        != selected_folder.get("camera_location")
        or _normalize_sync_limit((previous_folder or {}).get("max_files"))
        != selected_folder.get("max_files")
    )
    if folder_changed or settings_changed:
        reset_drive_sync_state(
            session,
            session_key,
            folder=selected_folder,
            message=(
                "Drive folder settings changed. Sync this folder again before running the pipeline."
                if settings_changed and not folder_changed
                else "Folder selection changed. Sync this folder before running the pipeline."
            ),
        )
    else:
        write_session(session, session_key)

    return {
        "message": "Folder selected successfully",
        "folder": selected_folder,
        "sync": serialize_drive_sync_state(
            session=read_session(session_key),
            session_key=session_key,
        ),
    }


@router.get("/selected-folder")
def get_selected_folder(authorization: Optional[str] = Header(default=None)):
    session_key, session = _require_auth_session(authorization)
    selected_folder = session.get("selected_drive_folder")

    return {
        "folder": selected_folder,
        "sync": serialize_drive_sync_state(session=session, session_key=session_key),
        "message": None if selected_folder else "No folder selected yet",
    }


@router.get("/sync-status")
def get_drive_sync_status(authorization: Optional[str] = Header(default=None)):
    session_key, session = _require_auth_session(authorization)
    return serialize_drive_sync_state(session=session, session_key=session_key)


@router.post("/sync/cancel")
def cancel_selected_folder_sync(authorization: Optional[str] = Header(default=None)):
    session_key, session = _require_auth_session(authorization)
    selected_folder = session.get("selected_drive_folder")
    state = cancel_drive_sync_operation(
        session,
        session_key,
        folder=selected_folder,
        message="Drive sync stopped by user",
    )
    return {
        "message": "Drive sync stop requested",
        "status": state.get("status"),
        "sync": serialize_drive_sync_state(
            session=read_session(session_key),
            session_key=session_key,
        ),
    }


@router.post("/sync")
def sync_selected_folder(
    payload: Optional[SyncFolderRequest] = None,
    authorization: Optional[str] = Header(default=None),
):
    session_key, session, google_auth, access_token = get_google_drive_auth_session(authorization)
    selected_folder = session.get("selected_drive_folder")

    if not selected_folder or not selected_folder.get("id"):
        raise HTTPException(
            status_code=400,
            detail="Select a Google Drive folder before starting a sync",
        )

    current_sync = serialize_drive_sync_state(session=session, session_key=session_key)
    if current_sync["status"] == "syncing":
        raise HTTPException(
            status_code=409,
            detail="A Drive sync is already in progress. Check /api/drive/sync-status for live progress.",
        )

    selected_folder["max_files"] = _normalize_sync_limit(
        payload.max_files if payload is not None else selected_folder.get("max_files")
    )
    selected_folder["camera_location"] = _normalize_camera_location(
        selected_folder.get("camera_location") or selected_folder.get("name")
    )
    session["selected_drive_folder"] = selected_folder
    write_session(session, session_key)

    requested_total_for_start = 0
    try:
        requested_total_for_start = max(0, int(selected_folder.get("max_files") or 0))
    except (TypeError, ValueError):
        requested_total_for_start = 0
    start_drive_sync_operation(
        session,
        session_key,
        folder=selected_folder,
        staging_dir=str(resolve_pipeline_staging_dir()),
        requested_total=requested_total_for_start,
        message=(
            f"Syncing {selected_folder.get('name') or selected_folder['id']} "
            "into backend staging"
        ),
    )
    cancel_token = get_drive_sync_cancel_token(session_key)

    def progress_callback(progress: Dict[str, Any]) -> None:
        downloaded = int(progress.get("downloaded_count") or 0)
        discovered = int(progress.get("discovered_count") or 0)
        failed = int(progress.get("failed_count") or 0)
        skipped = int(progress.get("already_staged_count") or progress.get("skipped_count") or 0)
        discovery_complete = bool(progress.get("discovery_complete"))
        requested_total = int(progress.get("requested_total") or 0)
        # Pick a sensible message: while listing is still in progress we
        # talk about the *requested* target if the user set one, else just
        # say "discovering and downloading". After listing completes we
        # know the real total.
        if discovery_complete:
            message = f"Downloaded {downloaded} of total {discovered} image(s)"
        elif requested_total > 0:
            message = (
                f"Downloaded {downloaded} of {requested_total} requested"
                f" · {discovered} discovered so far"
            )
        else:
            message = (
                f"Discovering and downloading… {downloaded} downloaded,"
                f" {discovered} discovered so far"
            )
        if skipped:
            message += f" · {skipped} skipped"
        if failed:
            message += f" · {failed} failed"
        update_drive_sync_progress(
            session_key,
            folder=selected_folder,
            discovered_count=discovered,
            downloaded_count=downloaded,
            current_file=progress.get("current_file"),
            staging_dir=progress.get("staging_dir"),
            message=message,
            failed_count=failed,
            skipped_count=skipped,
            discovery_complete=discovery_complete,
            requested_total=requested_total,
            images_per_second=progress.get("images_per_second"),
            eta_seconds=progress.get("eta_seconds"),
            elapsed_seconds=progress.get("elapsed_seconds"),
        )

    try:
        sync_result = stage_selected_drive_folder(
            access_token=access_token,
            refresh_token=google_auth.get("refresh_token"),
            folder_id=selected_folder["id"],
            folder_name=selected_folder.get("name") or selected_folder["id"],
            camera_location=selected_folder.get("camera_location"),
            staging_dir=resolve_pipeline_staging_dir(),
            max_files=selected_folder.get("max_files"),
            progress_callback=progress_callback,
            cancellation_token=cancel_token,
        )
        if cancel_token and cancel_token.is_cancelled():
            raise OperationCancelled("Drive sync stopped by user")
        complete_drive_sync_operation(
            session,
            session_key,
            folder=selected_folder,
            sync_result=sync_result,
            message=(
                f"Synced {int(sync_result.get('downloaded_count') or 0)} image(s) "
                f"from {selected_folder.get('name') or selected_folder['id']}"
            ),
        )
    except OperationCancelled:
        cancel_drive_sync_operation(
            session,
            session_key,
            folder=selected_folder,
            message="Drive sync stopped by user",
        )
        return {
            "message": "Drive sync stopped",
            "folder": selected_folder,
            "sync": serialize_drive_sync_state(
                session=read_session(session_key),
                session_key=session_key,
            ),
            "result": None,
        }
    except FileNotFoundError as exc:
        fail_drive_sync_operation(
            session,
            session_key,
            folder=selected_folder,
            error=str(exc),
            message="Drive sync failed",
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        fail_drive_sync_operation(
            session,
            session_key,
            folder=selected_folder,
            error=f"Failed to sync the selected Drive folder: {exc}",
            message="Drive sync failed",
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sync the selected Drive folder: {exc}",
        ) from exc

    return {
        "message": "Drive folder synced into backend staging",
        "folder": selected_folder,
        "sync": serialize_drive_sync_state(
            session=read_session(session_key),
            session_key=session_key,
        ),
        "result": sync_result,
    }
