# downloads images using drive_index.csv as the source
# CHANGE: now reads from drive_index.csv instead of doing its own Drive API query
# This allows it to download files from nested folders that build_index.py already found

import csv
import io
from datetime import datetime
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# config 
SERVICE_ACCOUNT_FILE = "secrets/inf191a-uci-nature-sa.json"   # key file for service account auth

# CHANGE: now reads from drive_index.csv instead of querying Drive directly
DRIVE_INDEX = Path("data/outputs/drive_index.csv")            # source of file IDs to download

OUT_DIR = Path("data/staging")                                # where images get downloaded locally
LOG_CSV = Path("data/outputs/download_log.csv")               # download log

MAX_DOWNLOADS = 300
# this prevents us from clearing the full backlog
# we should consider removing or increasing this cap and adding a resume mechanism
# so downloads can continue across multiple runs without restarting

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]    # read only access


def make_local_name(file_id: str, original_name: str) -> str:
    return f"{file_id}__{original_name}"


def log(writer, file_name: str, file_id: str, status: str, error: str = "") -> None:
    writer.writerow({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "file_name": file_name,
        "file_id": file_id,
        "status": status,
        "error": error,
    })


def main() -> None:
    if not DRIVE_INDEX.exists():
        raise FileNotFoundError("drive_index.csv not found. Run build_index.py first.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_CSV.parent.mkdir(parents=True, exist_ok=True)

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )

    # create API client
    drive = build("drive", "v3", credentials=creds)

    downloaded = 0

    print(f"Reading file list from {DRIVE_INDEX}...")

    new_file = not LOG_CSV.exists()
    with open(LOG_CSV, "a", newline="", encoding="utf-8") as lf:
        writer = csv.DictWriter(
            lf, fieldnames=["timestamp", "file_name", "file_id", "status", "error"]
        )
        if new_file:
            writer.writeheader()

        # CHANGE: Read from drive_index.csv instead of calling Drive API list()
        # This gives us all files from nested folders that build_index.py already crawled
        with open(DRIVE_INDEX, "r", encoding="utf-8") as idx:
            reader = csv.DictReader(idx)
            
            for row in reader:
                file_id = row["file_id"]
                original_name = row["file_name"]

                # includes file_id to prevent collisions
                local_name = make_local_name(file_id, original_name)
                out_path = OUT_DIR / local_name

                # if already downloaded, don't download again
                if out_path.exists():
                    log(writer, original_name, file_id, "skip_exists")
                    continue

                try:
                    # download file content
                    request = drive.files().get_media(
                        fileId=file_id,
                        supportsAllDrives=True
                    )

                    # bytes to disk
                    with io.FileIO(out_path, "wb") as fh:
                        downloader = MediaIoBaseDownload(fh, request)
                        done = False
                        while not done:
                            _, done = downloader.next_chunk()

                    downloaded += 1
                    print(f"Downloaded {downloaded}: {local_name}")
                    log(writer, original_name, file_id, "success")

                except Exception as e:
                    # log errors
                    log(writer, original_name, file_id, "fail", repr(e))

                # stop after MAX_DOWNLOADS files
                if downloaded >= MAX_DOWNLOADS:
                    print(f"Done. Downloaded {downloaded} images to {OUT_DIR}")
                    print(f"Log saved to {LOG_CSV}")
                    return

    print(f"Done. Downloaded {downloaded} images to {OUT_DIR}")
    print(f"Log saved to {LOG_CSV}")


if __name__ == "__main__":
    main()