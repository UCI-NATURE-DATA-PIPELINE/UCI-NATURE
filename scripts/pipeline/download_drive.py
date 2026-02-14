# downloads images using drive_index.csv as the source
# CHANGE: now reads from drive_index.csv instead of doing its own Drive API query
# This allows it to download files from nested folders that build_index.py already found

import csv
import io
import time
from datetime import datetime
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

# config
from scripts.config import SERVICE_ACCOUNT_FILE, MAX_IMAGES

DRIVE_INDEX = Path("data/outputs/drive_index.csv")
OUT_DIR = Path("data/staging")
LOG_CSV = Path("data/outputs/download_log.csv")
PROGRESS_FILE = Path("data/outputs/.download_progress.csv")

MAX_DOWNLOADS = MAX_IMAGES  # from config.py
MAX_RETRIES = 3
RETRY_DELAY = 2

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]    # read only access


# def make_local_name(file_id: str, original_name: str) -> str:
#     return f"{file_id}__{original_name}"

def make_local_path(file_id: str, original_name: str, drive_path: str) -> Path:
    '''Takes 3 param and returns Path object'''
    if not drive_path:
        return OUT_DIR / f"{file_id}__{original_name}"

    # Remove filename from drive_path to get folder structure
    path_parts = Path(drive_path).parts[:-1]  # excluding filename itself

    # Build local folder path
    local_folder = OUT_DIR
    for part in path_parts:
        local_folder = local_folder / part

    # creating the local filename with prefix of file_id
    local_filename = f"{file_id}__{original_name}"

    return local_folder / local_filename


def log(writer, file_name: str, file_id: str, status: str, error: str = "") -> None:
    writer.writerow({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "file_name": file_name,
        "file_id": file_id,
        "status": status,
        "error": error,
    })


def load_already_downloaded() -> set:
    """Load set of file_ids that were already successfully downloaded"""
    downloaded = set()

    # Check progress file first
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("status") == "success":
                    downloaded.add(row.get("file_id", ""))

    # Also check existing files in staging directory (recursively)
    if OUT_DIR.exists():
        # searches "data/staging/**/* (all subdirectories recursively)"
        for path in OUT_DIR.rglob("*"):
            if path.is_file() and "__" in path.name:
                file_id = path.name.split("__")[0]
                downloaded.add(file_id)

    return downloaded


def save_progress(file_id: str, file_name: str, status: str, retry_count: int = 0):
    """Save download progress to resume file"""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Load existing progress
    progress = {}
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                progress[row["file_id"]] = row

    # Update with new status
    progress[file_id] = {
        "file_id": file_id,
        "file_name": file_name,
        "status": status,
        "retry_count": retry_count,
        "last_attempt": datetime.now().isoformat(timespec="seconds"),
    }

    # Write back
    with open(PROGRESS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["file_id", "file_name", "status", "retry_count", "last_attempt"]
        )
        writer.writeheader()
        writer.writerows(progress.values())


def download_file_with_retry(drive, file_id: str, original_name: str, out_path: Path,
                             log_writer, progress_lock: threading.Lock, log_lock: threading.Lock) -> bool:
    """Download a single file with retry logic"""

    # Create Parent directories
    out_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(MAX_RETRIES):
        try:
            request = drive.files().get_media(
                fileId=file_id,
                supportsAllDrives=True
            )

            with io.FileIO(out_path, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

            with progress_lock:
                save_progress(file_id, original_name, "success", attempt)
            with log_lock:
                log(log_writer, original_name, file_id, "success")
            return True

        except HttpError as e:
            error_msg = f"HttpError {e.resp.status}: {e.error_details}"

            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (2 ** attempt)
                time.sleep(delay)
                continue
            else:
                with progress_lock:
                    save_progress(file_id, original_name, "failed", attempt + 1)
                with log_lock:
                    log(log_writer, original_name, file_id, "fail", error_msg)
                return False

        except Exception as e:
            error_msg = repr(e)

            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (2 ** attempt)
                time.sleep(delay)
                continue
            else:
                with progress_lock:
                    save_progress(file_id, original_name, "failed", attempt + 1)
                with log_lock:
                    log(log_writer, original_name, file_id, "fail", error_msg)
                return False

    return False


def main() -> None:
    if not DRIVE_INDEX.exists():
        raise FileNotFoundError("drive_index.csv not found. Run build_index.py first.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_CSV.parent.mkdir(parents=True, exist_ok=True)

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )

    already_downloaded = load_already_downloaded()
    print(f"Found {len(already_downloaded)} already downloaded files (will skip)")

    downloaded = 0
    skipped = 0
    failed = 0

    print(f"Reading file list from {DRIVE_INDEX}...")

    new_file = not LOG_CSV.exists()
    progress_lock = threading.Lock()
    log_lock = threading.Lock()

    thread_local = threading.local()

    def get_drive():
        drive = getattr(thread_local, "drive", None)
        if drive is None:
            thread_local.drive = build("drive", "v3", credentials=creds, cache_discovery=False)
            drive = thread_local.drive
        return drive

    def worker(file_id: str, original_name: str, out_path: Path):
        return download_file_with_retry(
            get_drive(),
            file_id,
            original_name,
            out_path,
            writer,
            progress_lock,
            log_lock
        )

    with open(LOG_CSV, "a", newline="", encoding="utf-8") as lf:
        writer = csv.DictWriter(
            lf, fieldnames=["timestamp", "file_name", "file_id", "status", "error"]
        )
        if new_file:
            writer.writeheader()

        with open(DRIVE_INDEX, "r", encoding="utf-8") as idx:
            reader = csv.DictReader(idx)

            to_download = []
            for row in reader:
                file_id = row["file_id"]
                original_name = row["file_name"]
                drive_path = row.get("drive_path", "")

                out_path = make_local_path(file_id, original_name, drive_path)

                if file_id in already_downloaded and out_path.exists():
                    skipped += 1
                    if skipped % 50 == 0:
                        print(f"Skipped {skipped} already-downloaded files...")
                    continue

                to_download.append((file_id, original_name, out_path))

            if MAX_DOWNLOADS is not None:
                to_download = to_download[:MAX_DOWNLOADS]

            limit_str = "∞" if MAX_DOWNLOADS is None else str(MAX_DOWNLOADS)
            max_workers = 12

            try:
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    future_map = {
                        pool.submit(worker, file_id, original_name, out_path): (out_path, original_name)
                        for (file_id, original_name, out_path) in to_download
                    }

                    for fut in as_completed(future_map):
                        out_path, original_name = future_map[fut]
                        ok = fut.result()
                        if ok:
                            downloaded += 1
                            rel_path = out_path.relative_to(OUT_DIR)
                            print(f"Downloaded {downloaded}/{limit_str}: {rel_path}")
                        else:
                            failed += 1
                            print(f"Failed to download: {original_name}")

                        if MAX_DOWNLOADS is not None and downloaded >= MAX_DOWNLOADS:
                            break

            except KeyboardInterrupt:
                print("\nInterrupted.")
                print(f"Successfully downloaded: {downloaded}")
                print(f"Skipped (already exists): {skipped}")
                print(f"Failed: {failed}")
                print(f"Files saved to: {OUT_DIR}")
                print(f"Log saved to: {LOG_CSV}")
                print(f"Progress saved to: {PROGRESS_FILE}")
                return

    print(f"\nDownload complete!")
    print(f"Successfully downloaded: {downloaded}")
    print(f"Skipped (already exists): {skipped}")
    print(f"Failed: {failed}")
    print(f"Files saved to: {OUT_DIR}")
    print(f"Log saved to: {LOG_CSV}")
    print(f"Progress saved to: {PROGRESS_FILE}")


if __name__ == "__main__":
    main()
