from __future__ import annotations

import csv
import io
import json
import os
import queue
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple, Union

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from scripts.config import GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET


REPO_ROOT = Path(__file__).resolve().parents[3]
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".tif", ".tiff"}
SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/heic",
    "image/heif",
    "image/webp",
    "image/tiff",
    "image/x-tiff",
}
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
SHORTCUT_MIME_TYPE = "application/vnd.google-apps.shortcut"
DEFAULT_DRIVE_INDEX_PATH = Path("data/outputs/drive_index.csv")
DOWNLOAD_RETRY_ATTEMPTS = 5
RETRYABLE_DOWNLOAD_STATUS_CODES = {429, 500, 502, 503, 504}
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
STAGING_MANIFEST_NAME = ".drive_staging_manifest.json"
DRIVE_INDEX_CACHE_VERSION = 1
DRIVE_INDEX_CACHE_CSV_NAME = "drive_index_cache.csv"
DRIVE_INDEX_CACHE_MANIFEST_NAME = "drive_index_cache_manifest.json"


def _env_int(name: str, default: int, *, low: int = 1, high: int = 64) -> int:
    """Read a positive integer from the environment, clamped to [low, high]."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def _env_float(name: str, default: float, *, low: float = 0.0, high: float = 10.0) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Parallel-download tunables. Sensible defaults; override via env on AWS if
# the host has more cores / bandwidth.
DRIVE_DOWNLOAD_MAX_WORKERS = _env_int("UCI_NATURE_DRIVE_WORKERS", 8, low=1, high=32)
# Throttle how often progress_callback runs, so we don't write the session
# JSON 1000 times for a 1000-image sync (that destroys throughput on AWS EBS).
DRIVE_PROGRESS_MIN_INTERVAL_SECONDS = _env_float(
    "UCI_NATURE_DRIVE_PROGRESS_INTERVAL", 0.4, low=0.05, high=5.0
)
# Per-file "Downloaded: ..." prints are off by default; flip this on for
# debugging a stuck sync.
DRIVE_DEBUG_LOG = _env_bool("UCI_NATURE_DRIVE_DEBUG", False)
DRIVE_INDEX_CACHE_ENABLED = _env_bool("UCI_NATURE_DRIVE_INDEX_CACHE", True)
DRIVE_INDEX_FIELDS = [
    "file_name",
    "file_id",
    "drive_folder_id",
    "mimeType",
    "modifiedTime",
    "size",
    "drive_path",
    "relative_local_path",
    "site",
    "deployment_folder",
    "deployment_id",
    "status",
]


def _repo_path(path: Union[Path, str]) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False


def _resolve_safe_staging_dir(path: Union[Path, str]) -> Path:
    resolved_path = _repo_path(path).resolve()
    data_root = (REPO_ROOT / "data").resolve()

    if not _is_relative_to(resolved_path, data_root):
        raise RuntimeError(
            f"Refusing to clear staging outside the repository data directory: {resolved_path}"
        )

    if resolved_path == data_root:
        raise RuntimeError(
            f"Refusing to clear the repository data root as a staging directory: {resolved_path}"
        )

    return resolved_path


def _sanitize_name(name: str) -> str:
    cleaned = (name or "").replace("/", "_").replace("\\", "_").strip()
    return cleaned or "untitled"


def _is_supported_image(file_name: str, mime_type: str) -> bool:
    normalized_mime_type = (mime_type or "").strip().lower()
    if normalized_mime_type in SUPPORTED_IMAGE_MIME_TYPES:
        return True
    return Path(file_name or "").suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS


def _new_drive_listing_stats() -> Dict[str, object]:
    return {
        "folders_scanned": 0,
        "files_scanned": 0,
        "images_discovered": 0,
        "first_image_names": [],
    }


def _increment_listing_stat(stats: Optional[Dict[str, object]], key: str) -> None:
    if stats is None:
        return
    stats[key] = int(stats.get(key) or 0) + 1


def _record_listing_image(stats: Optional[Dict[str, object]], file_name: str) -> None:
    if stats is None:
        return
    _increment_listing_stat(stats, "images_discovered")
    first_names = stats.setdefault("first_image_names", [])
    if isinstance(first_names, list) and len(first_names) < 5:
        first_names.append(file_name)


def _get_drive_file_metadata(service, file_id: str) -> Dict[str, object]:
    return service.files().get(
        fileId=file_id,
        fields=(
            "id,name,mimeType,modifiedTime,size,driveId,webViewLink,"
            "shortcutDetails(targetId,targetMimeType)"
        ),
        supportsAllDrives=True,
    ).execute()


def _resolve_selected_drive_folder(
    service,
    folder_id: str,
    *,
    folder_name: str,
) -> Dict[str, object]:
    selected_id = str(folder_id or "").strip()
    if not selected_id:
        raise FileNotFoundError("No Google Drive folder id was provided")

    selected_metadata = _get_drive_file_metadata(service, selected_id)
    selected_mime_type = str(selected_metadata.get("mimeType") or "").strip()
    resolved_metadata = selected_metadata
    shortcut_target_id: Optional[str] = None
    seen_ids = {selected_id}

    while str(resolved_metadata.get("mimeType") or "").strip() == SHORTCUT_MIME_TYPE:
        details = resolved_metadata.get("shortcutDetails") or {}
        if not isinstance(details, dict):
            details = {}
        target_id = str(details.get("targetId") or "").strip()
        if not shortcut_target_id:
            shortcut_target_id = target_id or None
        if not target_id:
            raise FileNotFoundError(
                f"Google Drive shortcut {selected_id} does not expose a target folder id"
            )
        if target_id in seen_ids:
            raise FileNotFoundError(
                f"Google Drive shortcut {selected_id} resolves in a loop instead of a folder"
            )
        seen_ids.add(target_id)
        resolved_metadata = _get_drive_file_metadata(service, target_id)

    resolved_mime_type = str(resolved_metadata.get("mimeType") or "").strip()
    if resolved_mime_type != FOLDER_MIME_TYPE:
        display_name = str(selected_metadata.get("name") or folder_name or selected_id)
        raise FileNotFoundError(
            f"Selected Google Drive item is not a folder: {display_name} ({selected_id})"
        )

    resolved_id = str(resolved_metadata.get("id") or "").strip()
    if not resolved_id:
        raise FileNotFoundError(
            f"Unable to resolve the selected Google Drive folder id: {folder_name} ({selected_id})"
        )

    return {
        "selected_id": selected_id,
        "selected_name": str(selected_metadata.get("name") or folder_name or selected_id),
        "selected_mime_type": selected_mime_type,
        "shortcut_target_id": shortcut_target_id,
        "resolved_id": resolved_id,
        "resolved_name": str(resolved_metadata.get("name") or folder_name or resolved_id),
        "resolved_mime_type": resolved_mime_type,
    }


def _parse_drive_path(drive_path: str) -> Tuple[str, str, str, str]:
    parts = drive_path.split("/")
    site = parts[0] if parts else ""
    deployment_folder = parts[1] if len(parts) > 1 else ""
    deployment_id = ""
    status = ""

    if "_" in deployment_folder:
        prefix = deployment_folder.split("_", 1)[0]
        if prefix.isdigit():
            deployment_id = prefix

    if deployment_folder.endswith("_DONE"):
        status = "DONE"

    return site, deployment_folder, deployment_id, status


def _build_drive_service(access_token: str, refresh_token: Optional[str] = None):
    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URI if refresh_token else None,
        client_id=GOOGLE_OAUTH_CLIENT_ID if refresh_token else None,
        client_secret=GOOGLE_OAUTH_CLIENT_SECRET if refresh_token else None,
        scopes=[DRIVE_READONLY_SCOPE],
    )
    # cache_discovery=False avoids stale "discovery" warning spam and the
    # multi-MB import cost each time we build a new client per worker thread.
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _make_drive_service_factory(access_token: str, refresh_token: Optional[str]):
    """Return a callable that produces a thread-local Drive client.

    googleapiclient.discovery.Resource instances are not safe to share across
    threads. We hand each worker its own client (built lazily on first use)
    so parallel downloads don't trip over each other.
    """
    thread_local = threading.local()

    def get_service():
        existing = getattr(thread_local, "service", None)
        if existing is not None:
            return existing
        thread_local.service = _build_drive_service(access_token, refresh_token=refresh_token)
        return thread_local.service

    return get_service


def _iter_selected_folder_images(
    service,
    folder_id: str,
    *,
    seen_folders: Optional[Set[str]] = None,
    stats: Optional[Dict[str, object]] = None,
):
    stack: List[Tuple[str, Tuple[str, ...]]] = [(folder_id, ())]
    seen_folders = seen_folders if seen_folders is not None else set()

    while stack:
        current_folder_id, path_segments = stack.pop()
        if current_folder_id in seen_folders:
            continue
        seen_folders.add(current_folder_id)
        _increment_listing_stat(stats, "folders_scanned")

        page_token = None
        while True:
            response = service.files().list(
                q=f"'{current_folder_id}' in parents and trashed=false",
                fields=(
                    "nextPageToken, "
                    "files(id, name, mimeType, modifiedTime, size, "
                    "shortcutDetails(targetId,targetMimeType))"
                ),
                orderBy="name",
                pageSize=1000,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()

            for item in response.get("files", []):
                _increment_listing_stat(stats, "files_scanned")
                file_id = item.get("id", "")
                raw_name = item.get("name", "") or file_id
                safe_name = _sanitize_name(raw_name)
                mime_type = item.get("mimeType", "")
                next_segments = path_segments + (safe_name,)

                if mime_type == FOLDER_MIME_TYPE:
                    stack.append((file_id, next_segments))
                    continue

                if mime_type == SHORTCUT_MIME_TYPE:
                    details = item.get("shortcutDetails") or {}
                    if not isinstance(details, dict):
                        details = {}
                    target_id = str(details.get("targetId") or "").strip()
                    target_mime_type = ""
                    if target_id:
                        try:
                            target_metadata = _get_drive_file_metadata(service, target_id)
                            target_mime_type = str(target_metadata.get("mimeType") or "").strip()
                        except Exception as exc:  # noqa: BLE001 — skip broken shortcuts, keep listing
                            print(
                                "Drive listing skipped shortcut with unreadable target: "
                                f"{raw_name} ({file_id}) -> {target_id}: {exc!r}"
                            )
                            continue
                    if target_id and target_mime_type == FOLDER_MIME_TYPE:
                        stack.append((target_id, next_segments))
                    continue

                if not _is_supported_image(raw_name, mime_type):
                    continue

                _record_listing_image(stats, raw_name)
                drive_path = "/".join(next_segments)
                relative_local_path = (
                    Path(*path_segments) / f"{file_id}__{safe_name}"
                    if path_segments
                    else Path(f"{file_id}__{safe_name}")
                )
                yield {
                    "file_id": file_id,
                    "file_name": raw_name,
                    "drive_folder_id": current_folder_id,
                    "mimeType": mime_type,
                    "modifiedTime": item.get("modifiedTime", ""),
                    "size": item.get("size", ""),
                    "drive_path": drive_path,
                    "relative_local_path": relative_local_path,
                }

            page_token = response.get("nextPageToken")
            if not page_token:
                break


def _list_selected_folder_images(service, folder_id: str) -> List[Dict[str, object]]:
    files = list(_iter_selected_folder_images(service, folder_id))
    return sorted(files, key=lambda item: str(item["drive_path"]).lower())


def _download_file(service, file_id: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = Path(f"{out_path}.part")

    for attempt in range(1, DOWNLOAD_RETRY_ATTEMPTS + 1):
        request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
        try:
            with io.FileIO(temp_path, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            temp_path.replace(out_path)
            return
        except HttpError as exc:
            status_code = getattr(getattr(exc, "resp", None), "status", None)
            if temp_path.exists():
                temp_path.unlink()
            if status_code not in RETRYABLE_DOWNLOAD_STATUS_CODES or attempt >= DOWNLOAD_RETRY_ATTEMPTS:
                raise
            time.sleep(min(2 ** (attempt - 1), 5))
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            if attempt >= DOWNLOAD_RETRY_ATTEMPTS:
                raise
            time.sleep(min(2 ** (attempt - 1), 5))


def _emit_progress(
    progress_callback: Optional[Callable[[Dict[str, object]], None]],
    payload: Dict[str, object],
) -> None:
    if not progress_callback:
        return

    try:
        progress_callback(payload)
    except Exception:
        # Progress updates should never break the underlying sync.
        return


def _drive_index_cache_paths(index_path: Path) -> Tuple[Path, Path]:
    return (
        index_path.parent / DRIVE_INDEX_CACHE_CSV_NAME,
        index_path.parent / DRIVE_INDEX_CACHE_MANIFEST_NAME,
    )


def _normalize_relative_local_path(file_info: Dict[str, object]) -> Path:
    raw_relative_path = str(file_info.get("relative_local_path") or "").strip()
    if raw_relative_path:
        return Path(raw_relative_path)

    drive_path = str(file_info.get("drive_path") or "").strip()
    path_segments = [
        _sanitize_name(segment)
        for segment in drive_path.split("/")[:-1]
        if segment.strip()
    ]
    safe_name = _sanitize_name(str(file_info.get("file_name") or file_info.get("file_id") or "image"))
    file_id = str(file_info.get("file_id") or "").strip()
    local_name = f"{file_id}__{safe_name}" if file_id else safe_name
    return Path(*path_segments, local_name) if path_segments else Path(local_name)


def _row_to_file_info(row: Dict[str, str]) -> Dict[str, object]:
    file_info: Dict[str, object] = {
        "file_id": row.get("file_id", ""),
        "file_name": row.get("file_name", ""),
        "drive_folder_id": row.get("drive_folder_id", ""),
        "mimeType": row.get("mimeType", ""),
        "modifiedTime": row.get("modifiedTime", ""),
        "size": row.get("size", ""),
        "drive_path": row.get("drive_path", ""),
        "relative_local_path": row.get("relative_local_path", ""),
    }
    file_info["relative_local_path"] = _normalize_relative_local_path(file_info)
    return file_info


def _read_drive_index(index_path: Path) -> List[Dict[str, object]]:
    if not index_path.exists():
        return []

    try:
        with open(index_path, newline="", encoding="utf-8") as f:
            return [_row_to_file_info(row) for row in csv.DictReader(f)]
    except Exception:
        return []


def _write_drive_index(
    index_path: Path,
    files: List[Dict[str, object]],
    *,
    folder_name: str,
    camera_location: Optional[str] = None,
) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)

    with open(index_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=DRIVE_INDEX_FIELDS)
        writer.writeheader()
        for file_info in files:
            site, deployment_folder, deployment_id, status = _parse_drive_path(str(file_info["drive_path"]))
            fallback_location = (camera_location or folder_name or "").strip()
            if not deployment_folder and (not site or site == (file_info.get("file_name") or "").strip()):
                site = fallback_location
                deployment_folder = fallback_location
            writer.writerow({
                "file_name": file_info["file_name"],
                "file_id": file_info["file_id"],
                "drive_folder_id": file_info["drive_folder_id"],
                "mimeType": file_info["mimeType"],
                "modifiedTime": file_info["modifiedTime"],
                "size": file_info["size"],
                "drive_path": file_info["drive_path"],
                "relative_local_path": str(_normalize_relative_local_path(file_info)),
                "site": site,
                "deployment_folder": deployment_folder,
                "deployment_id": deployment_id,
                "status": status,
            })


def _read_drive_index_cache_manifest(manifest_path: Path) -> Optional[Dict[str, object]]:
    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None

    return payload if isinstance(payload, dict) else None


def _get_drive_start_page_token(service) -> Optional[str]:
    try:
        response = service.changes().getStartPageToken(
            supportsAllDrives=True,
        ).execute()
    except Exception as exc:
        print(f"Drive index cache token unavailable; cache validation will be skipped: {exc!r}")
        return None

    return str(response.get("startPageToken") or "").strip() or None


def _drive_cache_change_status(
    service,
    *,
    start_page_token: str,
    cached_files: List[Dict[str, object]],
    cached_folder_ids: Set[str],
) -> Tuple[bool, Optional[str]]:
    """Return (has_relevant_changes, new_start_page_token).

    We use the Drive Changes feed as a cheap cache validator. Any change to a
    cached file, a known folder, or a file whose parent is a known folder means
    the recursive tree may have changed and should be rebuilt.
    """
    known_file_ids = {
        str(file_info.get("file_id") or "").strip()
        for file_info in cached_files
        if str(file_info.get("file_id") or "").strip()
    }
    page_token = str(start_page_token or "").strip()
    new_start_page_token: Optional[str] = None

    if not page_token:
        return True, None

    while page_token:
        try:
            response = service.changes().list(
                pageToken=page_token,
                pageSize=1000,
                fields=(
                    "nextPageToken,newStartPageToken,"
                    "changes(fileId,removed,file(id,name,mimeType,modifiedTime,size,parents,trashed))"
                ),
                spaces="drive",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
        except HttpError as exc:
            status_code = getattr(getattr(exc, "resp", None), "status", None)
            if status_code == 410:
                print("Drive index cache token expired; rebuilding the recursive index.")
            else:
                print(f"Drive index cache validation failed; rebuilding recursive index: {exc!r}")
            return True, None
        except Exception as exc:
            print(f"Drive index cache validation failed; rebuilding recursive index: {exc!r}")
            return True, None

        for change in response.get("changes", []):
            file_id = str(change.get("fileId") or "").strip()
            if file_id in known_file_ids or file_id in cached_folder_ids:
                return True, response.get("newStartPageToken")

            changed_file = change.get("file") or {}
            parents = {str(parent).strip() for parent in changed_file.get("parents") or []}
            if parents & cached_folder_ids:
                return True, response.get("newStartPageToken")

            if change.get("removed") and file_id in known_file_ids:
                return True, response.get("newStartPageToken")

        page_token = response.get("nextPageToken")
        new_start_page_token = response.get("newStartPageToken") or new_start_page_token
        if not page_token:
            break

    return False, str(new_start_page_token or "").strip() or None


def _load_cached_drive_index(
    service,
    *,
    folder_id: str,
    cache_index_path: Path,
    cache_manifest_path: Path,
) -> Tuple[Optional[List[Dict[str, object]]], Optional[Dict[str, object]]]:
    if not DRIVE_INDEX_CACHE_ENABLED:
        return None, None

    manifest = _read_drive_index_cache_manifest(cache_manifest_path)
    if not manifest or int(manifest.get("version") or 0) != DRIVE_INDEX_CACHE_VERSION:
        return None, None

    if str(manifest.get("folder_id") or "").strip() != str(folder_id).strip():
        return None, None

    cached_files = _read_drive_index(cache_index_path)
    if not cached_files:
        print("Drive index cache has 0 images; falling back to live Drive listing")
        return None, None

    cached_folder_ids = {
        str(folder).strip()
        for folder in (manifest.get("folder_ids") or [])
        if str(folder).strip()
    }
    cached_folder_ids.add(str(folder_id).strip())

    changed, new_token = _drive_cache_change_status(
        service,
        start_page_token=str(manifest.get("start_page_token") or ""),
        cached_files=cached_files,
        cached_folder_ids=cached_folder_ids,
    )
    if changed:
        return None, None

    if new_token and new_token != manifest.get("start_page_token"):
        manifest = {
            **manifest,
            "start_page_token": new_token,
            "validated_at": time.time(),
        }
        _write_drive_index_cache_manifest(cache_manifest_path, manifest)

    print(
        f"Drive index cache hit: using {len(cached_files)} cached image(s) "
        f"from {cache_index_path}"
    )
    return cached_files, manifest


def _write_drive_index_cache_manifest(
    manifest_path: Path,
    payload: Dict[str, object],
) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    temp_path.replace(manifest_path)


def _write_drive_index_cache(
    *,
    cache_index_path: Path,
    cache_manifest_path: Path,
    files: List[Dict[str, object]],
    folder_ids: Set[str],
    folder_id: str,
    folder_name: str,
    camera_location: Optional[str],
    start_page_token: Optional[str],
) -> None:
    _write_drive_index(
        cache_index_path,
        files,
        folder_name=folder_name,
        camera_location=camera_location,
    )
    _write_drive_index_cache_manifest(
        cache_manifest_path,
        {
            "version": DRIVE_INDEX_CACHE_VERSION,
            "folder_id": folder_id,
            "folder_name": folder_name,
            "camera_location": camera_location,
            "indexed_at": time.time(),
            "file_count": len(files),
            "folder_ids": sorted(str(folder) for folder in folder_ids if str(folder).strip()),
            "cache_index_path": str(cache_index_path),
            "start_page_token": start_page_token,
        },
    )


def _clear_directory_contents(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _prune_unexpected_staging_files(
    staging_dir: Path,
    expected_relative_paths: Set[Path],
) -> int:
    if not staging_dir.exists():
        return 0

    expected = {Path(path) for path in expected_relative_paths}
    removed = 0
    for path in sorted(staging_dir.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
            continue

        rel_path = path.relative_to(staging_dir)
        if rel_path.name == STAGING_MANIFEST_NAME:
            continue
        if rel_path in expected:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass

    return removed


def _staging_manifest_path(staging_dir: Path) -> Path:
    return staging_dir / STAGING_MANIFEST_NAME


def _read_staging_manifest(staging_dir: Path) -> Optional[Dict[str, object]]:
    manifest_path = _staging_manifest_path(staging_dir)
    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    return payload


def _write_staging_manifest(
    staging_dir: Path,
    *,
    folder_id: str,
    folder_name: str,
    selected_folder_id: Optional[str] = None,
) -> Path:
    staging_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _staging_manifest_path(staging_dir)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "folder_id": folder_id,
                "selected_folder_id": selected_folder_id or folder_id,
                "folder_name": folder_name,
                "updated_at": time.time(),
            },
            f,
            indent=2,
        )
    return manifest_path


def stage_selected_drive_folder(
    *,
    access_token: Optional[str],
    refresh_token: Optional[str],
    folder_id: str,
    folder_name: str,
    camera_location: Optional[str] = None,
    staging_dir: Union[Path, str],
    drive_index_path: Path = DEFAULT_DRIVE_INDEX_PATH,
    max_files: Optional[int] = None,
    progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
) -> dict:
    if not access_token:
        raise RuntimeError(
            "A Google Drive folder is selected, but no Google OAuth access token is available for download."
        )

    resolved_staging_dir = _resolve_safe_staging_dir(staging_dir)
    resolved_drive_index_path = _repo_path(drive_index_path).resolve()
    cache_index_path, cache_manifest_path = _drive_index_cache_paths(resolved_drive_index_path)
    service = _build_drive_service(access_token, refresh_token=refresh_token)
    get_service = _make_drive_service_factory(access_token, refresh_token)

    print("Drive staging start")
    print(f"Selected Drive folder id: {folder_id}")
    print(f"Selected Drive folder name: {folder_name}")
    print(f"Drive staging target dir: {resolved_staging_dir}")
    print(
        f"Drive sync tunables: workers={DRIVE_DOWNLOAD_MAX_WORKERS} "
        f"progress_interval={DRIVE_PROGRESS_MIN_INTERVAL_SECONDS}s "
        f"debug_log={DRIVE_DEBUG_LOG} "
        f"index_cache={DRIVE_INDEX_CACHE_ENABLED}"
    )

    selected_folder_id = str(folder_id).strip()
    resolved_folder = _resolve_selected_drive_folder(
        service,
        selected_folder_id,
        folder_name=folder_name,
    )
    resolved_folder_id = str(resolved_folder["resolved_id"])
    print(f"Selected Drive folder mimeType: {resolved_folder.get('selected_mime_type') or '(unknown)'}")
    print(f"Drive shortcut target id: {resolved_folder.get('shortcut_target_id') or '(none)'}")
    print(f"Resolved Drive folder id: {resolved_folder_id}")
    print(f"Resolved Drive folder name: {resolved_folder.get('resolved_name') or folder_name}")

    existing_manifest = _read_staging_manifest(resolved_staging_dir)
    reset_staging = bool(
        existing_manifest is not None
        and str(existing_manifest.get("folder_id") or "").strip() != resolved_folder_id
    )
    if reset_staging:
        if resolved_staging_dir.exists() and any(resolved_staging_dir.iterdir()):
            _clear_directory_contents(resolved_staging_dir)
            print(
                "Cleared staging directory because the selected Drive source changed: "
                f"{resolved_staging_dir}"
            )
        else:
            resolved_staging_dir.mkdir(parents=True, exist_ok=True)
    resolved_staging_dir.mkdir(parents=True, exist_ok=True)
    _write_staging_manifest(
        resolved_staging_dir,
        folder_id=resolved_folder_id,
        folder_name=folder_name,
        selected_folder_id=selected_folder_id,
    )

    cached_files, cached_manifest = _load_cached_drive_index(
        service,
        folder_id=resolved_folder_id,
        cache_index_path=cache_index_path,
        cache_manifest_path=cache_manifest_path,
    )
    cache_hit = cached_files is not None
    files: List[Dict[str, object]] = []
    seen_folder_ids: Set[str] = set(cached_manifest.get("folder_ids") or []) if cached_manifest else set()
    cache_start_page_token = None if cache_hit else _get_drive_start_page_token(service)
    listing_stats = _new_drive_listing_stats()
    live_listing_completed = False

    # Fast skip: a file is considered already-staged if the final path exists
    # AND is non-empty. `.part` leftovers from previous interrupted syncs are
    # NOT counted, so they get re-downloaded cleanly.
    discovered_lock = threading.Lock()
    counters_lock = threading.Lock()
    discovered_total = 0
    target_count = 0
    already_staged_count = 0
    scheduled_download_count = 0
    downloaded_files: List[str] = []
    failed_files: List[Dict[str, object]] = []

    started_at_monotonic = time.monotonic()
    started_at_wall = time.time()
    last_progress_emit = [0.0]  # mutable holder for closure
    last_discovery_log = [0]
    last_download_log = [0]
    download_queue: "queue.Queue[Optional[Dict[str, object]]]" = queue.Queue(
        maxsize=max(DRIVE_DOWNLOAD_MAX_WORKERS * 4, 1)
    )

    def emit_running_progress(
        *,
        current_file: Optional[str],
        force: bool = False,
    ) -> None:
        """Push live progress to the UI, throttled by interval to avoid
        slamming the session JSON file (per-file emit dominated runtime)."""
        now = time.monotonic()
        # Always emit the very first event ("starting download...") and the
        # very last one ("done"); throttle the middle ones.
        if (
            not force
            and (now - last_progress_emit[0]) < DRIVE_PROGRESS_MIN_INTERVAL_SECONDS
        ):
            return
        last_progress_emit[0] = now

        with counters_lock:
            new_downloads = len(downloaded_files)
            failed = len(failed_files)
        with discovered_lock:
            current_target_count = target_count
            current_available_count = discovered_total
            current_skipped_count = already_staged_count
            current_staged_count = current_skipped_count + new_downloads
        elapsed = max(now - started_at_monotonic, 1e-6)
        ips = new_downloads / elapsed if elapsed > 0 else 0.0
        eta_seconds: Optional[float] = None
        remaining = max(current_target_count - current_staged_count - failed, 0)
        if ips > 0 and remaining > 0:
            eta_seconds = remaining / ips

        _emit_progress(
            progress_callback,
            {
                "event": "downloaded",
                "folder_id": selected_folder_id,
                "resolved_folder_id": resolved_folder_id,
                "folder_name": folder_name,
                "discovered_count": current_target_count,
                "downloaded_count": current_staged_count,
                "newly_downloaded_count": new_downloads,
                "failed_count": failed,
                "available_count": current_available_count,
                "already_staged_count": current_skipped_count,
                "skipped_count": current_skipped_count,
                "staged_count": current_staged_count,
                "remaining_count": remaining,
                "images_per_second": round(ips, 2),
                "eta_seconds": round(eta_seconds, 1) if eta_seconds is not None else None,
                "elapsed_seconds": round(elapsed, 1),
                "started_at": started_at_wall,
                "current_file": current_file,
                "staging_dir": str(resolved_staging_dir),
            },
        )

    def maybe_log_discovery(*, force: bool = False) -> None:
        with discovered_lock:
            current_available_count = discovered_total
            current_skipped_count = already_staged_count
        if force or current_available_count - last_discovery_log[0] >= 500:
            last_discovery_log[0] = current_available_count
            print(f"Discovered {current_available_count} images")
            print(f"Skipped already staged {current_skipped_count}")

    def maybe_log_download(*, force: bool = False) -> None:
        with counters_lock:
            new_downloads = len(downloaded_files)
        with discovered_lock:
            current_available_count = discovered_total
        if force or new_downloads - last_download_log[0] >= 100:
            last_download_log[0] = new_downloads
            print(f"Downloaded {new_downloads} / discovered {current_available_count}")

    def staged_path_for(file_info: Dict[str, object]) -> Path:
        return resolved_staging_dir / _normalize_relative_local_path(file_info)

    def is_already_staged(file_info: Dict[str, object]) -> bool:
        staged_path = staged_path_for(file_info)
        try:
            return staged_path.exists() and staged_path.stat().st_size > 0
        except OSError:
            return False

    def clean_partial_download(file_info: Dict[str, object]) -> None:
        staged_path = staged_path_for(file_info)
        part_path = staged_path.with_suffix(staged_path.suffix + ".part")
        if part_path.exists():
            try:
                part_path.unlink()
            except OSError:
                pass

    def record_discovered_file(file_info: Dict[str, object]) -> bool:
        nonlocal already_staged_count, discovered_total, scheduled_download_count, target_count

        file_info["relative_local_path"] = _normalize_relative_local_path(file_info)
        files.append(file_info)
        ready = is_already_staged(file_info)
        schedule = False
        with discovered_lock:
            discovered_total += 1
            if ready:
                already_staged_count += 1
                target_count += 1
            else:
                clean_partial_download(file_info)
                if max_files is None or scheduled_download_count < max(0, int(max_files)):
                    scheduled_download_count += 1
                    target_count += 1
                    schedule = True

        maybe_log_discovery()
        emit_running_progress(current_file=str(file_info.get("drive_path") or ""), force=False)
        return schedule

    def download_one(file_info: Dict[str, object]) -> Tuple[bool, Dict[str, object], Optional[str]]:
        out_path = staged_path_for(file_info)
        try:
            _download_file(get_service(), str(file_info["file_id"]), out_path)
            if DRIVE_DEBUG_LOG:
                print(f"Downloaded: {file_info['drive_path']} -> {out_path}")
            return True, file_info, None
        except Exception as exc:  # noqa: BLE001 — we want to keep going
            err = repr(exc)
            print(
                f"Drive sync failed for {file_info.get('drive_path')!r} "
                f"({file_info.get('file_id')!r}): {err}"
            )
            return False, file_info, err

    def download_worker() -> None:
        while True:
            file_info = download_queue.get()
            try:
                if file_info is None:
                    return
                ok, downloaded_info, error = download_one(file_info)
                with counters_lock:
                    if ok:
                        downloaded_files.append(str(_normalize_relative_local_path(downloaded_info)))
                    else:
                        failed_files.append({
                            "file_id": downloaded_info.get("file_id"),
                            "drive_path": downloaded_info.get("drive_path"),
                            "error": error,
                        })
                maybe_log_download()
                emit_running_progress(current_file=str(downloaded_info.get("drive_path") or ""))
            finally:
                download_queue.task_done()

    emit_running_progress(current_file=None, force=True)
    print(f"Download workers started: {DRIVE_DOWNLOAD_MAX_WORKERS}")

    with ThreadPoolExecutor(
        max_workers=DRIVE_DOWNLOAD_MAX_WORKERS,
        thread_name_prefix="drive-sync",
    ) as pool:
        worker_futures = [
            pool.submit(download_worker)
            for _ in range(DRIVE_DOWNLOAD_MAX_WORKERS)
        ]

        try:
            if cache_hit and cached_files is not None:
                files = []
                with discovered_lock:
                    seen_folder_ids.add(resolved_folder_id)
                print(f"Discovered {len(cached_files)} images from Drive index cache")
                for file_info in cached_files:
                    if record_discovered_file(file_info):
                        download_queue.put(file_info)
            else:
                print("Drive listing started")
                list_started = time.monotonic()
                for file_info in _iter_selected_folder_images(
                    service,
                    resolved_folder_id,
                    seen_folders=seen_folder_ids,
                    stats=listing_stats,
                ):
                    if record_discovered_file(file_info):
                        download_queue.put(file_info)
                live_listing_completed = True
                list_elapsed = time.monotonic() - list_started
                maybe_log_discovery(force=True)
                print(
                    f"Drive listing complete in {list_elapsed:.2f}s — "
                    f"{len(files)} supported image(s) discovered"
                )
        finally:
            for _ in range(DRIVE_DOWNLOAD_MAX_WORKERS):
                download_queue.put(None)

        for future in worker_futures:
            future.result()

    maybe_log_discovery(force=True)
    maybe_log_download(force=True)
    emit_running_progress(current_file=None, force=True)

    sync_elapsed = time.monotonic() - started_at_monotonic
    final_ips = (len(downloaded_files) / sync_elapsed) if sync_elapsed > 0 else 0.0
    available_count = len(files)
    if cache_hit:
        listing_folders_scanned = len(seen_folder_ids)
        listing_files_scanned = len(files)
        listing_images_discovered = len(files)
    else:
        listing_folders_scanned = int(listing_stats.get("folders_scanned") or 0)
        listing_files_scanned = int(listing_stats.get("files_scanned") or 0)
        listing_images_discovered = int(listing_stats.get("images_discovered") or 0)
    first_discovered_names = [
        str(file_info.get("file_name") or "")
        for file_info in files[:5]
        if str(file_info.get("file_name") or "").strip()
    ]
    print(
        "Drive listing summary: "
        f"folders_scanned={listing_folders_scanned} "
        f"files_scanned={listing_files_scanned} "
        f"images_discovered={listing_images_discovered}"
    )
    print(f"First discovered image names: {first_discovered_names}")

    if not files:
        if (
            live_listing_completed
            and listing_folders_scanned > 0
            and resolved_staging_dir.exists()
            and any(resolved_staging_dir.iterdir())
        ):
            _clear_directory_contents(resolved_staging_dir)
            print(f"Cleared staging directory because the selected Drive folder is empty: {resolved_staging_dir}")
        else:
            print(
                "Preserved staging directory because Drive listing did not complete "
                "a successful resolved-folder scan."
            )
        raise FileNotFoundError(
            f"No supported image files were found in the selected Google Drive folder: {folder_name} ({folder_id})"
        )

    removed_unexpected = _prune_unexpected_staging_files(
        resolved_staging_dir,
        {_normalize_relative_local_path(file_info) for file_info in files},
    )
    if removed_unexpected:
        print(f"Removed {removed_unexpected} unexpected staging file(s) not present in the Drive index")

    staged_files = [
        file_info
        for file_info in files
        if is_already_staged(file_info)
    ]
    staged_count = len(staged_files)

    if not cache_hit:
        _write_drive_index_cache(
            cache_index_path=cache_index_path,
            cache_manifest_path=cache_manifest_path,
            files=files,
            folder_ids=seen_folder_ids,
            folder_id=resolved_folder_id,
            folder_name=folder_name,
            camera_location=camera_location,
            start_page_token=cache_start_page_token,
        )

    _write_drive_index(
        resolved_drive_index_path,
        staged_files,
        folder_name=folder_name,
        camera_location=camera_location,
    )

    print(
        f"Drive sync done in {sync_elapsed:.2f}s — "
        f"downloaded={len(downloaded_files)} failed={len(failed_files)} "
        f"skipped_existing={already_staged_count} ips={final_ips:.2f}"
    )
    print(f"Supported image files discovered: {available_count}")
    print(f"Skipped already staged {already_staged_count}")
    print(f"Downloaded {len(downloaded_files)} / discovered {available_count}")
    print(f"Final staging dir path: {resolved_staging_dir}")
    print(f"Drive index written: {resolved_drive_index_path}")
    print(f"Drive index cache path: {cache_index_path}")

    return {
        "folder_id": selected_folder_id,
        "resolved_folder_id": resolved_folder_id,
        "folder_name": folder_name,
        "staging_dir": str(resolved_staging_dir),
        "drive_index_path": str(resolved_drive_index_path),
        "drive_index_cache_path": str(cache_index_path),
        "drive_index_cache_manifest_path": str(cache_manifest_path),
        "discovered_count": staged_count,
        "available_count": available_count,
        "downloaded_count": staged_count,
        "newly_downloaded_count": len(downloaded_files),
        "already_staged_count": already_staged_count,
        "failed_count": len(failed_files),
        "failed_files": failed_files,
        "remaining_count": max(available_count - staged_count, 0),
        "max_files": max_files,
        "downloaded_files": downloaded_files,
        "elapsed_seconds": round(sync_elapsed, 2),
        "images_per_second": round(final_ips, 2),
    }
