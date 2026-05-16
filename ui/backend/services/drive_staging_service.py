from __future__ import annotations

import csv
import io
import json
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple, Union

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from scripts.config import GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET


REPO_ROOT = Path(__file__).resolve().parents[3]
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
DEFAULT_DRIVE_INDEX_PATH = Path("data/outputs/drive_index.csv")
DOWNLOAD_RETRY_ATTEMPTS = 5
RETRYABLE_DOWNLOAD_STATUS_CODES = {429, 500, 502, 503, 504}
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
STAGING_MANIFEST_NAME = ".drive_staging_manifest.json"


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
DRIVE_INDEX_FIELDS = [
    "file_name",
    "file_id",
    "drive_folder_id",
    "mimeType",
    "modifiedTime",
    "size",
    "drive_path",
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
    del mime_type
    return Path(file_name).suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS


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


def _list_selected_folder_images(service, folder_id: str) -> List[Dict[str, object]]:
    stack: List[Tuple[str, Tuple[str, ...]]] = [(folder_id, ())]
    seen_folders: Set[str] = set()
    files: List[Dict[str, object]] = []

    while stack:
        current_folder_id, path_segments = stack.pop()
        if current_folder_id in seen_folders:
            continue
        seen_folders.add(current_folder_id)

        page_token = None
        while True:
            response = service.files().list(
                q=f"'{current_folder_id}' in parents and trashed=false",
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
                orderBy="name",
                pageSize=1000,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()

            for item in response.get("files", []):
                file_id = item.get("id", "")
                raw_name = item.get("name", "") or file_id
                safe_name = _sanitize_name(raw_name)
                mime_type = item.get("mimeType", "")
                next_segments = path_segments + (safe_name,)

                if mime_type == FOLDER_MIME_TYPE:
                    stack.append((file_id, next_segments))
                    continue

                if not _is_supported_image(raw_name, mime_type):
                    continue

                drive_path = "/".join(next_segments)
                relative_local_path = (
                    Path(*path_segments) / f"{file_id}__{safe_name}"
                    if path_segments
                    else Path(f"{file_id}__{safe_name}")
                )
                files.append({
                    "file_id": file_id,
                    "file_name": raw_name,
                    "drive_folder_id": current_folder_id,
                    "mimeType": mime_type,
                    "modifiedTime": item.get("modifiedTime", ""),
                    "size": item.get("size", ""),
                    "drive_path": drive_path,
                    "relative_local_path": relative_local_path,
                })

            page_token = response.get("nextPageToken")
            if not page_token:
                break

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
                "site": site,
                "deployment_folder": deployment_folder,
                "deployment_id": deployment_id,
                "status": status,
            })


def _clear_directory_contents(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


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


def _write_staging_manifest(staging_dir: Path, *, folder_id: str, folder_name: str) -> Path:
    staging_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _staging_manifest_path(staging_dir)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "folder_id": folder_id,
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
    # The listing step uses a single Drive client (sequential paginated calls).
    # Per-thread clients for downloads are produced by the factory below.
    service = _build_drive_service(access_token, refresh_token=refresh_token)
    get_service = _make_drive_service_factory(access_token, refresh_token)

    print("Drive staging start")
    print(f"Selected Drive folder id: {folder_id}")
    print(f"Selected Drive folder name: {folder_name}")
    print(f"Drive staging target dir: {resolved_staging_dir}")
    print(
        f"Drive sync tunables: workers={DRIVE_DOWNLOAD_MAX_WORKERS} "
        f"progress_interval={DRIVE_PROGRESS_MIN_INTERVAL_SECONDS}s "
        f"debug_log={DRIVE_DEBUG_LOG}"
    )

    list_started = time.monotonic()
    files = _list_selected_folder_images(service, folder_id)
    list_elapsed = time.monotonic() - list_started
    print(
        f"Drive listing complete in {list_elapsed:.2f}s — {len(files)} "
        "supported image(s) discovered"
    )
    available_count = len(files)
    if not files:
        if resolved_staging_dir.exists() and any(resolved_staging_dir.iterdir()):
            _clear_directory_contents(resolved_staging_dir)
            print(f"Cleared staging directory because the selected Drive folder is empty: {resolved_staging_dir}")
        raise FileNotFoundError(
            f"No supported image files were found in the selected Google Drive folder: {folder_name} ({folder_id})"
        )

    existing_manifest = _read_staging_manifest(resolved_staging_dir)
    reset_staging = bool(
        existing_manifest is None
        or str(existing_manifest.get("folder_id") or "").strip() != str(folder_id).strip()
    )
    if reset_staging:
        if resolved_staging_dir.exists() and any(resolved_staging_dir.iterdir()):
            _clear_directory_contents(resolved_staging_dir)
            print(
                "Cleared staging directory because the selected Drive source changed or "
                f"no Drive staging manifest was present: {resolved_staging_dir}"
            )
        else:
            resolved_staging_dir.mkdir(parents=True, exist_ok=True)
        _write_staging_manifest(
            resolved_staging_dir,
            folder_id=folder_id,
            folder_name=folder_name,
        )
    else:
        _write_staging_manifest(
            resolved_staging_dir,
            folder_id=folder_id,
            folder_name=folder_name,
        )

    # Fast skip: a file is considered already-staged if the final path exists
    # AND is non-empty. `.part` leftovers from previous interrupted syncs are
    # NOT counted, so they get re-downloaded cleanly.
    staged_files: List[Dict[str, object]] = []
    pending_files: List[Dict[str, object]] = []
    for file_info in files:
        staged_path = resolved_staging_dir / Path(file_info["relative_local_path"])
        try:
            ready = staged_path.exists() and staged_path.stat().st_size > 0
        except OSError:
            ready = False
        if ready:
            staged_files.append(file_info)
        else:
            # Clean obvious leftovers so the next attempt has a fresh path.
            part_path = staged_path.with_suffix(staged_path.suffix + ".part")
            if part_path.exists():
                try:
                    part_path.unlink()
                except OSError:
                    pass
            pending_files.append(file_info)

    already_staged_count = len(staged_files)
    remaining_unsynced_count = len(pending_files)
    files_to_download = pending_files
    if max_files is not None:
        limited_count = max(0, int(max_files))
        files_to_download = pending_files[:limited_count]
        if limited_count and remaining_unsynced_count > limited_count:
            print(
                f"Applying sync limit: downloading next {limited_count} of "
                f"{remaining_unsynced_count} unsynced image(s)"
            )

    discovered_count = len(files_to_download)
    print(f"Supported image files discovered: {available_count}")
    print(f"Already staged and skipped: {already_staged_count}")
    print(f"Pending unsynced images: {remaining_unsynced_count}")
    if not files_to_download:
        print("No new Drive files needed for this sync; using the existing staged cache.")
    _emit_progress(
        progress_callback,
        {
            "event": "discovered",
            "folder_id": folder_id,
            "folder_name": folder_name,
            "discovered_count": discovered_count,
            "downloaded_count": 0,
            "available_count": available_count,
            "already_staged_count": already_staged_count,
            "staged_count": already_staged_count,
            "remaining_count": remaining_unsynced_count,
            "current_file": None,
            "staging_dir": str(resolved_staging_dir),
        },
    )

    downloaded_files: List[str] = []
    failed_files: List[Dict[str, object]] = []

    counters_lock = threading.Lock()
    started_at_monotonic = time.monotonic()
    started_at_wall = time.time()
    last_progress_emit = [0.0]  # mutable holder for closure

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
            done = len(downloaded_files)
            failed = len(failed_files)
        elapsed = max(now - started_at_monotonic, 1e-6)
        ips = done / elapsed if elapsed > 0 else 0.0
        eta_seconds: Optional[float] = None
        remaining = max(discovered_count - done - failed, 0)
        if ips > 0 and remaining > 0:
            eta_seconds = remaining / ips

        _emit_progress(
            progress_callback,
            {
                "event": "downloaded",
                "folder_id": folder_id,
                "folder_name": folder_name,
                "discovered_count": discovered_count,
                "downloaded_count": done,
                "failed_count": failed,
                "available_count": available_count,
                "already_staged_count": already_staged_count,
                "staged_count": already_staged_count + done,
                "remaining_count": remaining,
                "images_per_second": round(ips, 2),
                "eta_seconds": round(eta_seconds, 1) if eta_seconds is not None else None,
                "elapsed_seconds": round(elapsed, 1),
                "started_at": started_at_wall,
                "current_file": current_file,
                "staging_dir": str(resolved_staging_dir),
            },
        )

    def download_one(file_info: Dict[str, object]) -> Tuple[bool, Dict[str, object], Optional[str]]:
        out_path = resolved_staging_dir / Path(file_info["relative_local_path"])
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

    # ── Parallel download fan-out ──────────────────────────────────────
    # 1 worker => current sequential behavior. The standalone CLI uses 16; we
    # default to 8 because the UI session token + Drive quota tends to be
    # more conservative under sustained parallelism.
    if files_to_download:
        emit_running_progress(current_file=None, force=True)

        with ThreadPoolExecutor(
            max_workers=DRIVE_DOWNLOAD_MAX_WORKERS,
            thread_name_prefix="drive-sync",
        ) as pool:
            future_map = {
                pool.submit(download_one, info): info for info in files_to_download
            }
            for future in as_completed(future_map):
                ok, file_info, error = future.result()
                with counters_lock:
                    if ok:
                        downloaded_files.append(str(file_info["relative_local_path"]))
                    else:
                        failed_files.append({
                            "file_id": file_info.get("file_id"),
                            "drive_path": file_info.get("drive_path"),
                            "error": error,
                        })
                emit_running_progress(current_file=str(file_info["drive_path"]))

        # Final emit so the UI lands on the exact final counts, no matter
        # what the throttle was doing on the last few completions.
        emit_running_progress(current_file=None, force=True)

    sync_elapsed = time.monotonic() - started_at_monotonic
    final_ips = (len(downloaded_files) / sync_elapsed) if sync_elapsed > 0 else 0.0

    staged_files = [
        file_info
        for file_info in files
        if (resolved_staging_dir / Path(file_info["relative_local_path"])).exists()
    ]
    staged_count = len(staged_files)

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
    print(f"Final staging dir path: {resolved_staging_dir}")
    print(f"Drive index written: {resolved_drive_index_path}")

    return {
        "folder_id": folder_id,
        "folder_name": folder_name,
        "staging_dir": str(resolved_staging_dir),
        "drive_index_path": str(resolved_drive_index_path),
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
