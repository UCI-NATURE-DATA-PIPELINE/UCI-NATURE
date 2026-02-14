# scripts/pipeline/download_drive.py
# downloads images using drive_index.csv as the source
# reads from drive_index_*.csv (or drive_index.csv) produced by build_index.py
# preserves folder structure under data/staging/
# supports resume + strict max_downloads cap + disk-space guard

import argparse
import csv
import io
import os
import time
from datetime import datetime
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

SERVICE_ACCOUNT_FILE = "secrets/inf191a-uci-nature-sa.json"
DRIVE_INDEX_DEFAULT = Path("data/outputs/drive_index.csv")

OUT_DIR = Path("data/staging")
LOG_CSV = Path("data/outputs/download_log.csv")
PROGRESS_FILE = Path("data/outputs/.download_progress.csv")

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds base (exponential backoff)

DEFAULT_MAX_WORKERS = 10
# Safety: stop before disk hits 0 (GB)
DEFAULT_MIN_FREE_GB = 2.0


def now_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def free_gb(path: Path) -> float:
    st = os.statvfs(str(path))
    return (st.f_bavail * st.f_frsize) / (1024 ** 3)


def make_local_path(file_id: str, original_name: str, drive_path: str) -> Path:
    if not drive_path:
        return OUT_DIR / f"{file_id}__{original_name}"

    parts = Path(drive_path).parts[:-1]  # remove filename
    local_folder = OUT_DIR
    for part in parts:
        local_folder = local_folder / part

    local_filename = f"{file_id}__{original_name}"
    return local_folder / local_filename


def load_already_downloaded(resume: bool) -> set[str]:
    downloaded: set[str] = set()

    # progress file
    if resume and PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("status") == "success":
                    fid = (row.get("file_id") or "").strip()
                    if fid:
                        downloaded.add(fid)

    # scan staging
    if OUT_DIR.exists():
        for p in OUT_DIR.rglob("*"):
            if p.is_file() and "__" in p.name:
                fid = p.name.split("__", 1)[0].strip()
                if fid:
                    downloaded.add(fid)

    return downloaded


def append_progress(progress_writer, file_id: str, file_name: str, status: str, retry_count: int):
    progress_writer.writerow({
        "timestamp": now_ts(),
        "file_id": file_id,
        "file_name": file_name,
        "status": status,
        "retry_count": retry_count,
    })


def append_log(log_writer, file_name: str, file_id: str, status: str, error: str = ""):
    log_writer.writerow({
        "timestamp": now_ts(),
        "file_name": file_name,
        "file_id": file_id,
        "status": status,
        "error": error,
    })


def download_one(drive, file_id: str, original_name: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)

    # write to a temp file first, then rename (avoids half-written files)
    tmp_path = out_path.with_name("." + out_path.name + ".part")

    with io.FileIO(tmp_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

    tmp_path.replace(out_path)


def download_file_with_retry(
    drive,
    file_id: str,
    original_name: str,
    out_path: Path,
    log_writer,
    progress_writer,
    io_lock: threading.Lock,
    stop_flag: threading.Event,
    min_free_gb: float,
) -> bool:
    for attempt in range(MAX_RETRIES):
        if stop_flag.is_set():
            return False

        # disk guard
        if free_gb(Path(".")) < min_free_gb:
            with io_lock:
                append_log(log_writer, original_name, file_id, "fail", f"low_disk<{min_free_gb}GB")
                append_progress(progress_writer, file_id, original_name, "failed", attempt)
            stop_flag.set()
            return False

        try:
            download_one(drive, file_id, original_name, out_path)
            with io_lock:
                append_log(log_writer, original_name, file_id, "success", "")
                append_progress(progress_writer, file_id, original_name, "success", attempt)
            return True

        except OSError as e:
            # Catch disk-full mid-download
            if "No space left on device" in str(e):
                with io_lock:
                    append_log(log_writer, original_name, file_id, "fail", "no_space_left")
                    append_progress(progress_writer, file_id, original_name, "failed", attempt + 1)
                stop_flag.set()
                return False
            err = repr(e)

        except HttpError as e:
            err = f"HttpError {getattr(e.resp,'status', '?')}: {getattr(e,'error_details', '')}"

        except Exception as e:
            err = repr(e)

        # retry
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY * (2 ** attempt))
        else:
            with io_lock:
                append_log(log_writer, original_name, file_id, "fail", err)
                append_progress(progress_writer, file_id, original_name, "failed", attempt + 1)
            return False

    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", default=str(DRIVE_INDEX_DEFAULT))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max_downloads", type=int, default=10000)  # HARD DEFAULT CAP
    parser.add_argument("--workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--min_free_gb", type=float, default=DEFAULT_MIN_FREE_GB)
    args = parser.parse_args()

    drive_index = Path(args.index)
    if not drive_index.exists():
        raise FileNotFoundError(f"Index not found: {drive_index}")

    max_workers = max(1, int(args.workers))
    min_free_gb = float(args.min_free_gb)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_CSV.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)

    already = load_already_downloaded(args.resume)
    if args.resume:
        print(f"Resume ON: already downloaded = {len(already)}")

    target = int(args.max_downloads)
    remaining_slots = max(0, target - len(already))
    if remaining_slots == 0:
        print(f"Already have >= {target} files. Nothing to do.")
        return

    # creds (this should work once disk is not full)
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )

    thread_local = threading.local()

    def get_drive():
        d = getattr(thread_local, "drive", None)
        if d is None:
            thread_local.drive = build("drive", "v3", credentials=creds, cache_discovery=False)
            d = thread_local.drive
        return d

    # open log + progress append-only
    new_log = not LOG_CSV.exists()
    new_prog = not PROGRESS_FILE.exists()

    io_lock = threading.Lock()
    stop_flag = threading.Event()

    downloaded = 0
    skipped = 0
    failed = 0

    with open(LOG_CSV, "a", newline="", encoding="utf-8") as lf, \
         open(PROGRESS_FILE, "a", newline="", encoding="utf-8") as pf:

        log_writer = csv.DictWriter(lf, fieldnames=["timestamp", "file_name", "file_id", "status", "error"])
        prog_writer = csv.DictWriter(pf, fieldnames=["timestamp", "file_id", "file_name", "status", "retry_count"])

        if new_log:
            log_writer.writeheader()
        if new_prog:
            prog_writer.writeheader()

        # Build a bounded queue up front: ONLY enqueue remaining_slots
        to_download = []
        with open(drive_index, "r", encoding="utf-8") as idx:
            reader = csv.DictReader(idx)
            for row in reader:
                fid = (row.get("file_id") or "").strip()
                name = (row.get("file_name") or "").strip()
                drive_path = (row.get("drive_path") or row.get("local_path") or "").strip()

                if not fid or not name:
                    continue

                out_path = make_local_path(fid, name, drive_path)

                if fid in already and out_path.exists():
                    skipped += 1
                    continue

                to_download.append((fid, name, out_path))
                if len(to_download) >= remaining_slots:
                    break

        print(f"Target cap: {target}")
        print(f"Will download: {len(to_download)} (skipped so far: {skipped})")
        print(f"Workers: {max_workers}, Min free GB: {min_free_gb}")

        def worker(fid, name, out_path):
            return download_file_with_retry(
                get_drive(), fid, name, out_path,
                log_writer, prog_writer,
                io_lock, stop_flag,
                min_free_gb
            )

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_map = {
                pool.submit(worker, fid, name, out_path): (fid, name, out_path)
                for (fid, name, out_path) in to_download
            }

            for fut in as_completed(future_map):
                fid, name, out_path = future_map[fut]
                try:
                    ok = fut.result()
                except Exception as e:
                    ok = False
                    with io_lock:
                        append_log(log_writer, name, fid, "fail", f"worker_exception:{repr(e)}")
                        append_progress(prog_writer, fid, name, "failed", MAX_RETRIES)

                if ok:
                    downloaded += 1
                    rel = out_path.relative_to(OUT_DIR)
                    print(f"Downloaded {downloaded}/{len(to_download)}: {rel}")
                else:
                    failed += 1
                    print(f"Failed: {name}")
                    if stop_flag.is_set():
                        print("Stopping early due to disk guard / no space.")
                        break

    print("\nDownload summary")
    print(f"  downloaded: {downloaded}")
    print(f"  skipped:    {skipped}")
    print(f"  failed:     {failed}")
    print(f"  staging:    {OUT_DIR}")
    print(f"  log:        {LOG_CSV}")
    print(f"  progress:   {PROGRESS_FILE}")


if __name__ == "__main__":
    main()