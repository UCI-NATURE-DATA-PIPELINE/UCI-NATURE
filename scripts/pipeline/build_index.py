## makes a CSV index of everything inside the Drive folder (ids + basic metadata)
# new: recursive + drive_path + parsed folder fields (site, deployment info)

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


def list_children_with_retry(drive, folder_id: str):
    """List folder children with retry logic"""
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
                
                # Success - break retry loop
                break
                
            except HttpError as e:
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY * (2 ** attempt)
                    print(f"  API error (attempt {attempt + 1}): {e.resp.status}")
                    print(f"  Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    print(f"  Failed after {MAX_RETRIES} attempts")
                    raise
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY * (2 ** attempt)
                    print(f"  Error (attempt {attempt + 1}): {repr(e)}")
                    print(f"  Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    raise

        for item in resp.get("files", []):
            yield item

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

def load_checkpoint():
    """Load existing progress from checkpoint file"""
    if not CHECKPOINT_FILE.exists():
        return [], set()
    
    rows = []
    seen = set()
    
    with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
            seen.add(row["file_id"])
    
    print(f"Resuming from checkpoint: {len(rows)} rows already indexed")
    return rows, seen


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
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    drive = build("drive", "v3", credentials=creds)

    # Load checkpoint if exists
    rows, indexed_ids = load_checkpoint()

    stack = [(FOLDER_ID, "")]
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
                
                # Skip if already indexed (for resume)
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

                # Periodic checkpoint
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

    # Sort and save final output
    rows.sort(key=lambda r: r["drive_path"])
    save_final_output(rows)

    print(f"wrote {len(rows)} rows -> {OUT_CSV}")
    if rows:
        print("Example path:", rows[0]["drive_path"])
    
    # Clean up checkpoint file on success
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print("Checkpoint file removed (indexing complete)")


if __name__ == "__main__":
    main()