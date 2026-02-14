## makes a CSV index of everything inside the Drive folder (ids + basic metadata)
# recursive + drive_path + parsed folder fields (site, deployment info)
# skips folders we don't want to process (OLD, other studies, etc.)

import argparse
import csv
import re
import time
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SERVICE_ACCOUNT_FILE = "secrets/inf191a-uci-nature-sa.json"
FOLDER_ID = "0ACQBvZlfUN2CUk9PVA"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

OUT_CSV = Path("data/outputs/drive_index.csv")
CHECKPOINT_FILE = Path("data/outputs/.index_checkpoint.csv")

FIELDS = [
    "file_name", "file_id", "drive_folder_id", "mimeType", "modifiedTime", "size",
    "drive_path",
    "site", "deployment_folder", "deployment_id", "status",
]

FOLDER_MIMETYPE = "application/vnd.google-apps.folder"

PRINT_EVERY = 500
MAX_ROWS = 300        # None = unlimited, set a number for testing
CHECKPOINT_EVERY = 100
MAX_RETRIES = 3
RETRY_DELAY = 2

# Folders to skip (don't process images from these)
SKIP_FOLDERS = {
    "OLD Locations (Deprecated Cameras)",
    "Data From Other Camera Studies",
    "Summer 2023 MSWE AI Image Processing",
    "*** PHOTO PROCESSING STARTS HERE ***",
    "*** Field Upload START HERE ***",
}


def parse_drive_path(drive_path: str):
    parts = drive_path.split("/")
    site = parts[0] if parts else ""

    deployment_folder = parts[1] if len(parts) > 1 else ""
    deployment_id = ""
    status = ""

    m = re.match(r"^(\d{1,3})_", deployment_folder)
    if m:
        deployment_id = m.group(1)

    if deployment_folder.endswith("_DONE"):
        status = "DONE"

    return site, deployment_folder, deployment_id, status


def should_skip_path(drive_path: str) -> bool:
    """Check if this path should be skipped based on SKIP_FOLDERS."""
    for part in drive_path.split("/"):
        if part in SKIP_FOLDERS:
            return True
    return False


def list_children(drive, folder_id: str):
    """List folder children with retry logic."""
    query = f"'{folder_id}' in parents and trashed = false"
    page_token = None

    while True:
        for attempt in range(MAX_RETRIES):
            try:
                resp = drive.files().list(
                    q=query,
                    fields="nextPageToken, files(id,name,mimeType,modifiedTime,size,parents)",
                    pageSize=1000,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                ).execute()
                break
            except (HttpError, Exception) as e:
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY * (2 ** attempt)
                    print(f"  API error (attempt {attempt + 1}): {e}")
                    print(f"  Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    raise

        for item in resp.get("files", []):
            yield item

        page_token = resp.get("nextPageToken")
        if not page_token:
            break


def load_checkpoint(checkpoint_file: Path):
    """Load existing progress from checkpoint file."""
    if not checkpoint_file.exists():
        return [], set()
    rows = []
    seen = set()
    with open(checkpoint_file, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
            seen.add(row["file_id"])
    print(f"Resuming from checkpoint: {len(rows)} rows already indexed")
    return rows, seen


def save_checkpoint(rows, checkpoint_file: Path):
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def parse_id_list(value):
    if not value:
        return []
    return [s.strip() for s in str(value).split(",") if s.strip()]


def init_drive():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def write_output_csv(rows, out_csv: Path):
    rows.sort(key=lambda r: r["drive_path"])
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def make_run_tag(drive_root: str, start_folders: str | None):
    ids = parse_id_list(start_folders)
    if ids:
        return "_".join(ids)
    return drive_root


def resolve_paths(args):
    if args.per_folder:
        tag = make_run_tag(args.drive_root, args.start_folders)
        out_csv = Path("data/outputs") / f"drive_index_{tag}.csv"
        checkpoint_file = Path("data/outputs") / f".index_checkpoint_{tag}.csv"
        return out_csv, checkpoint_file

    out_csv = Path(args.out) if args.out else OUT_CSV
    checkpoint_file = Path(args.checkpoint_file) if args.checkpoint_file else CHECKPOINT_FILE
    return out_csv, checkpoint_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive_root", default=FOLDER_ID)
    parser.add_argument("--start_folders", default=None)
    parser.add_argument("--out", default=str(OUT_CSV))
    parser.add_argument("--checkpoint_file", default=None)
    parser.add_argument("--per_folder", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max_files", type=int, default=None)
    args = parser.parse_args()

    out_csv, checkpoint_file = resolve_paths(args)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    drive = init_drive()

    if args.resume:
        rows, indexed_ids = load_checkpoint(checkpoint_file)
    else:
        rows, indexed_ids = [], set()
        if checkpoint_file.exists():
            checkpoint_file.unlink()

    skipped_count = 0

    start_ids = parse_id_list(args.start_folders)
    if start_ids:
        stack = [(fid, "") for fid in start_ids]
    else:
        stack = [(args.drive_root, "")]

    seen = set()
    folders_done = 0

    max_rows = args.max_files if args.max_files is not None else MAX_ROWS

    try:
        while stack:
            current_folder_id, prefix = stack.pop()

            if current_folder_id in seen:
                continue
            seen.add(current_folder_id)

            folders_done += 1
            if folders_done % 25 == 0:
                print(f"folders visited: {folders_done}, rows so far: {len(rows)}, skipped: {skipped_count}")

            for item in list_children(drive, current_folder_id):
                name = item.get("name", "")
                drive_path = f"{prefix}/{name}" if prefix else name

                # Skip unwanted folders
                if should_skip_path(drive_path):
                    if item.get("mimeType") == FOLDER_MIMETYPE:
                        skipped_count += 1
                        if skipped_count <= 5:
                            print(f"Skipping folder: {drive_path}")
                    continue

                if item.get("mimeType") == FOLDER_MIMETYPE:
                    stack.append((item["id"], drive_path))
                    continue

                if not item.get("mimeType", "").startswith("image/"):
                    continue

                file_id = item.get("id", "")
                if file_id in indexed_ids:
                    continue

                parents = item.get("parents") or [current_folder_id]
                site, deployment_folder, deployment_id, status = parse_drive_path(drive_path)

                rows.append({
                    "file_name": name,
                    "file_id": file_id,
                    "drive_folder_id": parents[0],
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
                    print(f"rows indexed: {len(rows)}")

                if len(rows) % CHECKPOINT_EVERY == 0:
                    save_checkpoint(rows, checkpoint_file)

                if max_rows is not None and len(rows) >= max_rows:
                    print(f"stopping early at MAX_ROWS={max_rows}")
                    stack.clear()
                    break

    except KeyboardInterrupt:
        print("\nInterrupted! Saving checkpoint...")
        save_checkpoint(rows, checkpoint_file)
        print(f"Checkpoint saved with {len(rows)} rows. Run again to resume.")
        return
    except Exception as e:
        print(f"\nError: {repr(e)}")
        save_checkpoint(rows, checkpoint_file)
        raise

    write_output_csv(rows, out_csv)

    print(f"\nwrote {len(rows)} rows -> {out_csv}")
    print(f"skipped {skipped_count} folders")
    if rows:
        print("Example path:", rows[0]["drive_path"])
        sites = sorted(set(r["site"] for r in rows if r["site"]))
        print(f"\nLocations found:")
        for site in sites:
            count = sum(1 for r in rows if r["site"] == site)
            print(f"  - {site}: {count} images")

    if checkpoint_file.exists():
        checkpoint_file.unlink()


if __name__ == "__main__":
    main()