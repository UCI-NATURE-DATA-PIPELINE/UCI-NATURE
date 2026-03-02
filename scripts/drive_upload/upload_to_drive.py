"""
Upload camera-specific CSV files to Google Drive with append logic.
IMPROVED: Appends new rows only - no need to download the entire existing CSV.
Duplicate detection by Image# is deferred for future implementation.
"""

import csv
import io
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

# CSV filename in Drive (same for all cameras)
DRIVE_CSV_NAME = "TEST_DO_NOT_USE_wildlife_results.csv" #"wildlife_results.csv"

# Camera folder IDs in Google Drive (Julie's Shared Drive)
CAMERA_FOLDERS = {
    "Research_Park": "1rzbNvk_a9rtYMYBGdL-XYtdvKNpOmoqE",
    "Bonita_Canyon1": "1dPUQx1j7WaA1iKA0HUxWTju-aacfRbZz",
    "Bonita_Canyon2": "1nsuuDXHyeV5gdjgS3_MV7FyIdfbLEiEQ",
    "Marshtrail": "1CjxfyveXI-ZS-G8G3rcyQMY--MVvFiY2",
}

FIELDNAMES = [
    "CameraName", "DeploymentFolder", "Image#", "Species",
    "# of Individuals", "Date", "Time", "has_animal",
    "model_certainty", "Notes"
]


def find_file_in_folder(drive, folder_id: str, filename: str):
    """Check if file exists in Drive folder, return file metadata or None"""
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    results = drive.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    files = results.get('files', [])
    return files[0] if files else None


def rows_to_csv_bytes(rows: list[dict], include_header: bool) -> bytes:
    """Convert rows to CSV bytes for upload"""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDNAMES)
    if include_header:
        writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def create_csv_in_drive(drive, folder_id: str, filename: str, rows: list[dict]):
    """Create a brand new CSV file in Drive with header + rows"""
    content = rows_to_csv_bytes(rows, include_header=True)

    file_metadata = {
        "name": filename,
        "parents": [folder_id]
        # "mimeType": "application/vnd.google-apps.spreadsheet"
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


def append_rows_to_drive_csv(drive, file_id: str, new_rows: list[dict]):
    """
    Append new rows to existing CSV in Drive.
    Downloads only the existing file's content to check for duplicates by Image#.
    NOTE: Full duplicate detection deferred - currently appends all new rows.
    """
    # Download existing file to get current Image# values
    request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    from googleapiclient.http import MediaIoBaseDownload
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    buf.seek(0)
    existing_content = buf.read().decode("utf-8")

    # Get existing Image# values to skip duplicates
    existing_image_nums = set()
    reader = csv.DictReader(io.StringIO(existing_content))
    for row in reader:
        img = (row.get("Image#") or "").strip()
        if img:
            existing_image_nums.add(img)

    # Filter out duplicates
    rows_to_append = [
        r for r in new_rows
        if (r.get("Image#") or "").strip() not in existing_image_nums
    ]

    skipped = len(new_rows) - len(rows_to_append)
    if skipped:
        print(f"  Skipped {skipped} duplicate rows (by Image#)")

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


def process_camera(drive, camera_name: str, folder_id: str, local_csv: Path):
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
        append_rows_to_drive_csv(drive, existing_file['id'], new_rows)
        print(f"  ✓ Done - appended to existing file")
    else:
        print(f"  No existing CSV found - creating new file...")
        created = create_csv_in_drive(drive, folder_id, DRIVE_CSV_NAME, new_rows)
        print(f"  ✓ Created new CSV (ID: {created['id']}) with {len(new_rows)} rows")


def main():
    if not BY_LOCATION_DIR.exists():
        raise FileNotFoundError(
            f"{BY_LOCATION_DIR} not found. Run make_output.py first."
        )

    print("Authenticating with Google Drive...")
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    drive = build("drive", "v3", credentials=creds)

    print("\n" + "=" * 60)
    print("UPLOADING RESULTS TO GOOGLE DRIVE")
    print("=" * 60)

    for camera_name, folder_id in CAMERA_FOLDERS.items():
        local_csv = BY_LOCATION_DIR / f"{camera_name}_results.csv"

        if not local_csv.exists():
            print(f"\nSkipping {camera_name}: no local CSV found")
            continue

        try:
            process_camera(drive, camera_name, folder_id, local_csv)
        except HttpError as e:
            print(f"\nError processing {camera_name}: {e}")
            continue

    print("\n" + "=" * 60)
    print("UPLOAD COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()