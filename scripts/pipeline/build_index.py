## makes a CSV index of everything inside the Drive folder (ids + basic metadata)
# new: recursive + drive_path + parsed folder fields (site, deployment info)

import argparse
import sys
import csv
import re
import time
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from scripts.config import SERVICE_ACCOUNT_FILE as DEFAULT_SERVICE_ACCOUNT_FILE
    from scripts.config import FOLDER_ID as DEFAULT_FOLDER_ID
except Exception:
    DEFAULT_SERVICE_ACCOUNT_FILE = SERVICE_ACCOUNT_FILE
    DEFAULT_FOLDER_ID = FOLDER_ID

SERVICE_ACCOUNT_FILE = "secrets/inf191a-uci-nature-sa.json"
DEFAULT_SERVICE_ACCOUNT_FILE = "secrets/inf191a-uci-nature-sa.json"
FOLDER_ID = "0ACQBvZlfUN2CUk9PVA"
DEFAULT_FOLDER_ID = "0ACQBvZlfUN2CUk9PVA"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

OUT_CSV = Path("data/outputs/drive_index.csv")
CHECKPOINT_FILE = Path("data/outputs/.index_checkpoint.csv")  # NEW: for resuming

FIELDS = [
    "file_name", "file_id", "drive_folder_id", "mimeType", "modifiedTime", "size",
    "drive_path",
    "site", "deployment_folder", "deployment_id", "status",
]

FOLDER_MIMETYPE = "application/vnd.google-apps.folder"      # crawl folders

PRINT_EVERY = 500
MAX_ROWS = 2000
CHECKPOINT_EVERY = 100  # NEW: save checkpoint every N rows
MAX_RETRIES = 3         # NEW: retry API calls
RETRY_DELAY = 2         # NEW: initial delay for retries


def parse_id_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


def make_run_tag(drive_root: str | None, start_folders: str | None) -> str:
    ids = parse_id_list(start_folders)
    if ids:
        return "_".join(ids)
    return drive_root or ""


def parse_drive_path(drive_path: str):
    parts = drive_path.split("/")
    site = parts[0] if parts else ""

    deployment_folder = parts[1] if len(parts) > 1 else ""
    deployment_id = ""
    status = ""

    # deployment folder looks like "123_DeploymentName_DONE" or "123_DeploymentName"
    m = re.match(r"^(\d{1,3})_", deployment_folder)
    if m:
        deployment_id = m.group(1)

    if deployment_folder.endswith("_DONE"):
        status = "DONE"

    return site, deployment_folder, deployment_id, status


def list_children_with_retry(drive, folder_id: str):
    """List children with retries for transient errors"""
    delay = RETRY_DELAY
    for attempt in range(MAX_RETRIES):
        try:
            items = []
            page_token = None
            while True:
                resp = drive.files().list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
                    pageSize=1000,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    corpora="drive",
                    driveId=FOLDER_ID,
                ).execute()
                items.extend(resp.get("files", []))
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
            return items
        except HttpError as e:
            if attempt == MAX_RETRIES - 1:
                raise
            print(f"HttpError listing folder {folder_id}: {e}. retrying in {delay}s")
            time.sleep(delay)
            delay *= 2
    return []


def load_checkpoint():
    """Load checkpoint rows and set of file_ids already indexed"""
    if not CHECKPOINT_FILE.exists():
        return [], set()

    rows = []
    indexed_ids = set()
    with open(CHECKPOINT_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
            if r.get("file_id"):
                indexed_ids.add(r["file_id"])
    print(f"loaded checkpoint: {len(rows)} rows")
    return rows, indexed_ids


def save_checkpoint(rows):
    """Save current progress to checkpoint file"""
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(CHECKPOINT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def save_final_output(rows):
    """Save final CSV output"""
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    global SERVICE_ACCOUNT_FILE, FOLDER_ID, OUT_CSV, CHECKPOINT_FILE, MAX_ROWS

    ap = argparse.ArgumentParser(description="Build a CSV index of everything inside the Drive folder (recursive).")
    ap.add_argument("--drive_root", default=DEFAULT_FOLDER_ID, help="Root Drive folder ID to index.")
    ap.add_argument("--start_folders", default=None, help="Comma-separated folder IDs to start from (overrides drive_root).")
    ap.add_argument("--out", default=None, help="Output CSV path.")
    ap.add_argument("--per_folder", action="store_true", help="Name output using a run tag (drive_index_<id>.csv).")
    ap.add_argument("--resume", action="store_true", help="Resume from checkpoint if present.")
    ap.add_argument("--max_files", type=int, default=None, help="Stop after indexing this many files.")
    ap.add_argument("--service_account_file", default=DEFAULT_SERVICE_ACCOUNT_FILE, help="Path to Google service account JSON.")
    args = ap.parse_args()

    SERVICE_ACCOUNT_FILE = args.service_account_file
    FOLDER_ID = args.drive_root or DEFAULT_FOLDER_ID

    if args.out:
        OUT_CSV = Path(args.out)
    elif args.per_folder:
        tag = make_run_tag(args.drive_root, args.start_folders)
        OUT_CSV = Path("data/outputs") / (f"drive_index_{tag}.csv" if tag else "drive_index.csv")
    else:
        OUT_CSV = Path("data/outputs/drive_index.csv")

    CHECKPOINT_FILE = OUT_CSV.with_name(".index_checkpoint_" + OUT_CSV.name)

    if args.max_files is not None:
        MAX_ROWS = args.max_files

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    drive = build("drive", "v3", credentials=creds)

    if args.resume:
        rows, indexed_ids = load_checkpoint()
    else:
        rows, indexed_ids = [], set()

    start_ids = parse_id_list(args.start_folders) if args.start_folders else []
    if not start_ids:
        start_ids = [FOLDER_ID]

    stack = [(fid, "") for fid in start_ids]
    seen = set()
    folders_done = 0

    try:
        while stack:
            current_folder_id, prefix = stack.pop()

            if current_folder_id in seen:
                continue
            seen.add(current_folder_id)

            folders_done += 1
            if folders_done % 25 == 0:
                print(f"folders visited: {folders_done}, rows so far: {len(rows)}")

            for item in list_children_with_retry(drive, current_folder_id):
                name = item.get("name", "")
                drive_path = f"{prefix}/{name}" if prefix else name

                if item.get("mimeType") == FOLDER_MIMETYPE:
                    stack.append((item["id"], drive_path))
                    continue

                if not item.get("mimeType", "").startswith("image/"):
                    continue

                file_id = item.get("id", "")

                if file_id in indexed_ids:
                    continue

                site, deployment_folder, deployment_id, status = parse_drive_path(drive_path)

                rows.append({
                    "file_name": name,
                    "file_id": file_id,
                    "drive_folder_id": current_folder_id,
                    "mimeType": item.get("mimeType", ""),
                    "modifiedTime": item.get("modifiedTime", ""),
                    "size": item.get("size", ""),
                    "drive_path": drive_path,
                    "site": site,
                    "deployment_folder": deployment_folder,
                    "deployment_id": deployment_id,
                    "status": status,
                })
                indexed_ids.add(file_id)

                if len(rows) % PRINT_EVERY == 0:
                    print(f" rows indexed: {len(rows)}")

                if len(rows) % CHECKPOINT_EVERY == 0:
                    save_checkpoint(rows)

                if MAX_ROWS is not None and len(rows) >= MAX_ROWS:
                    print(f"stopping early at MAX_ROWS={MAX_ROWS}")
                    stack.clear()
                    break

    except KeyboardInterrupt:
        print("\nInterrupted! Saving checkpoint...")
        save_checkpoint(rows)
        print(f"Checkpoint saved with {len(rows)} rows")
        print(f"Run again to resume from checkpoint")
        return
    except Exception as e:
        print(f"\nError occurred: {repr(e)}")
        print("Saving checkpoint before exit...")
        save_checkpoint(rows)
        raise

    rows.sort(key=lambda r: r["drive_path"])
    save_final_output(rows)

    print(f"wrote {len(rows)} rows -> {OUT_CSV}")
    if rows:
        print("Example path:", rows[0]["drive_path"])

    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print("Checkpoint file removed (indexing complete)")


if __name__ == "__main__":
    main()
    