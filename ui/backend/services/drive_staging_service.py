from __future__ import annotations

import csv
import io
import json
import shutil
import time
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
DOWNLOAD_RETRY_ATTEMPTS = 8
RETRYABLE_DOWNLOAD_STATUS_CODES = {500, 502, 503, 504}
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
STAGING_MANIFEST_NAME = ".drive_staging_manifest.json"
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
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


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
    service = _build_drive_service(access_token, refresh_token=refresh_token)

    print("Drive staging start")
    print(f"Selected Drive folder id: {folder_id}")
    print(f"Selected Drive folder name: {folder_name}")
    print(f"Drive staging target dir: {resolved_staging_dir}")

    files = _list_selected_folder_images(service, folder_id)
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

    staged_files: List[Dict[str, object]] = []
    pending_files: List[Dict[str, object]] = []
    for file_info in files:
        staged_path = resolved_staging_dir / Path(file_info["relative_local_path"])
        if staged_path.exists():
            staged_files.append(file_info)
        else:
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
    for index, file_info in enumerate(files_to_download, start=1):
        out_path = resolved_staging_dir / Path(file_info["relative_local_path"])
        _download_file(service, str(file_info["file_id"]), out_path)
        downloaded_files.append(str(file_info["relative_local_path"]))
        print(f"Downloaded: {file_info['drive_path']} -> {out_path}")
        _emit_progress(
            progress_callback,
            {
                "event": "downloaded",
                "folder_id": folder_id,
                "folder_name": folder_name,
                "discovered_count": discovered_count,
                "downloaded_count": index,
                "available_count": available_count,
                "already_staged_count": already_staged_count,
                "staged_count": already_staged_count + index,
                "remaining_count": max(remaining_unsynced_count - index, 0),
                "current_file": str(file_info["drive_path"]),
                "staging_dir": str(resolved_staging_dir),
            },
        )

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

    print(f"Files downloaded: {len(downloaded_files)}")
    print(f"Files staged total: {staged_count}")
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
        "remaining_count": max(available_count - staged_count, 0),
        "max_files": max_files,
        "downloaded_files": downloaded_files,
    }
