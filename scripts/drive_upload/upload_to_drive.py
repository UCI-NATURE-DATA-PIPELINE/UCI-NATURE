from typing import Optional
"""
Upload camera-specific CSV files to Google Drive with append logic.
IMPROVED: Appends new rows only - no need to download the entire existing CSV.
Duplicate detection by Image# is deferred for future implementation.
"""

import csv
import io
import re
import argparse
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError

# Config
SERVICE_ACCOUNT_FILE = "secrets/inf191a-uci-nature-sa.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# Local CSVs directory
BY_LOCATION_DIR = Path("data/outputs/by_location")
DRIVE_INDEX = Path("data/outputs/drive_index.csv")

# CSV filename in Drive (same for all cameras)
DRIVE_CSV_NAME = "wildlife_results.csv"  # "TEST_DO_NOT_USE_wildlife_results.csv"

FIELDNAMES = [
    "CameraName", "DeploymentFolder", "Image#", "Species",
    "# of Individuals", "CorrectedSpecies", "Corrected# of Individuals",
    "HasMultipleSpecies", "SecondarySpecies", "Secondary# of Individuals",
    "Date", "Time", "CorrectedDate", "CorrectedTime",
    "has_animal", "model_certainty", "Notes"
]


SHEETS_MIME = "application/vnd.google-apps.spreadsheet"


def build_camera_deployment_map(drive_index_path: Path) -> dict[str, str]:
    """Build camera_name -> deployment_folder_id from drive_index.csv using the
    same naming logic as make_output.py (strip date prefix + _DONE suffix)."""
    mapping: dict[str, str] = {}
    if not drive_index_path.exists():
        return mapping
    with open(drive_index_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            deployment = (row.get("deployment_folder") or "").strip()
            folder_id = (row.get("drive_folder_id") or "").strip()
            if not deployment or not folder_id:
                continue
            name = re.sub(r'^\d{4}_\d{2}_\d{2}_', '', deployment)
            name = re.sub(r'_DONE$', '', name, flags=re.IGNORECASE)
            name = name.replace(" ", "")
            if name and name not in mapping:
                mapping[name] = folder_id
    return mapping


def get_parent_folder_id(drive, folder_id: str) -> Optional[str]:
    """Return the parent folder ID of a given Drive folder."""
    try:
        result = drive.files().get(
            fileId=folder_id,
            fields="parents",
            supportsAllDrives=True
        ).execute()
        parents = result.get("parents", [])
        return parents[0] if parents else None
    except HttpError:
        return None


def find_file_in_folder(drive, folder_id: str, filename: str):
    """Check if file exists in Drive folder, return file metadata or None"""
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    results = drive.files().list(
        q=query,
        fields="files(id, name, mimeType)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    files = results.get('files', [])
    return files[0] if files else None


def rows_to_csv_bytes(rows: list[dict], include_header: bool) -> bytes:
    """Convert rows to CSV bytes for upload"""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDNAMES, extrasaction="ignore")
    if include_header:
        writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def create_csv_in_drive(drive, folder_id: str, filename: str, rows: list[dict]):
    """Create a brand new CSV file in Drive with header + rows"""
    content = rows_to_csv_bytes(rows, include_header=True)

    file_metadata = {
        "name": filename,
        "parents": [folder_id],
        "mimeType": SHEETS_MIME,
    }
    media = MediaIoBaseUpload(
        io.BytesIO(content),
        mimetype="text/csv",
        resumable=False
    )
    file = drive.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name",
        supportsAllDrives=True
    ).execute()
    return file


def overwrite_csv_in_drive(drive, file_id: str, rows: list[dict]):
    content = rows_to_csv_bytes(rows, include_header=True)
    media = MediaIoBaseUpload(
        io.BytesIO(content),
        mimetype="text/csv",
        resumable=False
    )
    drive.files().update(
        fileId=file_id,
        media_body=media,
        supportsAllDrives=True
    ).execute()


def append_rows_to_drive_csv(drive, file_id: str, new_rows: list[dict], file_mime: str = "text/csv"):
    """
    Append new rows to existing CSV in Drive.
    Downloads only the existing file's content to check for duplicates by Image#.
    NOTE: Full duplicate detection deferred - currently appends all new rows.
    """
    def _row_key(row: dict) -> str:
        dep = (row.get("DeploymentFolder") or "").strip()
        img = (row.get("Image#") or "").strip()
        cam = (row.get("CameraName") or "").strip()
        date = (row.get("Date") or "").strip()
        time_val = (row.get("Time") or "").strip()

        if dep and img:
            return f"{dep}|{img}"
        if cam and date and time_val and img:
            return f"{cam}|{date}|{time_val}|{img}"
        if img:
            return img
        return ""

    # Download existing file to get current Image# values to skip duplicates by key
    from googleapiclient.http import MediaIoBaseDownload
    if file_mime == SHEETS_MIME:
        request = drive.files().export_media(fileId=file_id, mimeType="text/csv")
    else:
        request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    buf.seek(0)
    existing_content = buf.read().decode("utf-8")

    # Get existing keys to skip duplicates
    existing_keys = set()
    reader = csv.DictReader(io.StringIO(existing_content))
    for row in reader:
        k = _row_key(row)
        if k:
            existing_keys.add(k)

    # Filter out duplicates
    rows_to_append = []
    for r in new_rows:
        k = _row_key(r)
        if k and k in existing_keys:
            continue
        rows_to_append.append(r)
        if k:
            existing_keys.add(k)

    skipped = len(new_rows) - len(rows_to_append)
    if skipped:
        print(f"  Skipped {skipped} duplicate rows (by DeploymentFolder|Image#)")

    if not rows_to_append:
        print(f"  No new rows to append - all already exist")
        return

    # Build new content = existing + new rows (no header for appended rows)
    append_content = rows_to_csv_bytes(rows_to_append, include_header=False)
    full_content = existing_content.rstrip("\n") + "\n" + append_content.decode("utf-8")

    media = MediaIoBaseUpload(
        io.BytesIO(full_content.encode("utf-8")),
        mimetype="text/csv",
        resumable=False
    )
    drive.files().update(
        fileId=file_id,
        media_body=media,
        supportsAllDrives=True
    ).execute()

    print(f"  Appended {len(rows_to_append)} new rows")


def process_camera(drive, camera_name: str, folder_id: str, local_csv: Path, overwrite: bool):
    """Process one camera: create new CSV or append to existing"""
    print(f"\nProcessing {camera_name}...")

    # Load new rows from local CSV
    with open(local_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        new_rows = list(reader)

    print(f"  Local rows to upload: {len(new_rows)}")

    # Check if CSV already exists in Drive
    existing_file = find_file_in_folder(drive, folder_id, DRIVE_CSV_NAME)

    if existing_file:
        print(f"  Found existing CSV in Drive (ID: {existing_file['id']})")
        if overwrite:
            overwrite_csv_in_drive(drive, existing_file['id'], new_rows)
            print(f"  ✓ Overwrote existing file")
        else:
            append_rows_to_drive_csv(drive, existing_file['id'], new_rows, existing_file.get('mimeType', 'text/csv'))
            print(f"  ✓ Done - appended to existing file")
    else:
        print(f"  No existing CSV found - creating new file...")
        created = create_csv_in_drive(drive, folder_id, DRIVE_CSV_NAME, new_rows)
        print(f"  ✓ Created new CSV (ID: {created['id']}) with {len(new_rows)} rows")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if not BY_LOCATION_DIR.exists():
        raise FileNotFoundError(
            f"{BY_LOCATION_DIR} not found. Run make_output.py first."
        )

    print("Authenticating with Google Drive...")
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    drive = build("drive", "v3", credentials=creds)

    deployment_map = build_camera_deployment_map(DRIVE_INDEX)
    if not deployment_map:
        print("WARNING: drive_index.csv not found or empty — cannot determine Drive folder IDs.")

    # Resolve each deployment folder → its site-level parent folder (cache to avoid duplicate API calls)
    parent_cache: dict[str, str] = {}
    camera_folders: dict[str, str] = {}
    for camera_name, dep_folder_id in deployment_map.items():
        if dep_folder_id not in parent_cache:
            parent_id = get_parent_folder_id(drive, dep_folder_id)
            if parent_id:
                parent_cache[dep_folder_id] = parent_id
        if dep_folder_id in parent_cache:
            camera_folders[camera_name] = parent_cache[dep_folder_id]

    print("\n" + "=" * 60)
    print("UPLOADING RESULTS TO GOOGLE DRIVE")
    print("=" * 60)

    for local_csv in sorted(BY_LOCATION_DIR.glob("*.csv")):
        camera_name = local_csv.stem
        folder_id = camera_folders.get(camera_name)
        if not folder_id:
            print(f"\nSkipping {camera_name}: no matching Drive folder found in drive_index.csv")
            continue

        try:
            process_camera(drive, camera_name, folder_id, local_csv, args.overwrite)
        except HttpError as e:
            print(f"\nError processing {camera_name}: {e}")
            continue

    print("\n" + "=" * 60)
    print("UPLOAD COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()