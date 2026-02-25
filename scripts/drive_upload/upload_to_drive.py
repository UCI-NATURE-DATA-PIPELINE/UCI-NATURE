"""
Upload camera-specific CSV files to Google Drive with append logic.
Uploads to correct camera folders and merges with existing CSVs.
"""

import csv
import io
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# Config
SERVICE_ACCOUNT_FILE = "secrets/inf191a-uci-nature-sa.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# Local CSVs directory
BY_LOCATION_DIR = Path("data/outputs/by_location")

# CSV filename in Drive (same for all cameras)
DRIVE_CSV_NAME = "wildlife_results.csv"

# Camera folder IDs in Google Drive
# TODO: Run find_camera_folders.py to get these IDs
CAMERA_FOLDERS = {
    "Research_Park": "FOLDER_ID_HERE",
    "Bonita_Canyon1": "FOLDER_ID_HERE",
    "Bonita_Canyon2": "FOLDER_ID_HERE",
    "Marshtrail": "FOLDER_ID_HERE",
}


def find_file_in_folder(drive, folder_id: str, filename: str):
    """Check if file exists in Drive folder"""
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    
    results = drive.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    
    files = results.get('files', [])
    return files[0] if files else None


def download_csv_from_drive(drive, file_id: str) -> list[dict]:
    """Download existing CSV from Drive and return rows"""
    request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
    
    file_handle = io.BytesIO()
    downloader = MediaIoBaseDownload(file_handle, request)
    
    done = False
    while not done:
        _, done = downloader.next_chunk()
    
    file_handle.seek(0)
    content = file_handle.read().decode('utf-8')
    
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


def merge_csvs(existing_rows: list[dict], new_rows: list[dict]) -> list[dict]:
    """
    Merge existing and new CSV data.
    Deduplicates by Image# (keeps most recent).
    """
    # Index existing rows by Image#
    by_image = {}
    for row in existing_rows:
        image_num = row.get("Image#", "")
        if image_num:
            by_image[image_num] = row
    
    # Add/update with new rows
    for row in new_rows:
        image_num = row.get("Image#", "")
        if image_num:
            by_image[image_num] = row  # Overwrites if duplicate
    
    # Return merged list
    return list(by_image.values())


def upload_csv_to_drive(drive, folder_id: str, csv_path: Path, filename: str):
    """Upload CSV to Drive folder"""
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    
    media = MediaFileUpload(
        str(csv_path),
        mimetype='text/csv',
        resumable=True
    )
    
    file = drive.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, name',
        supportsAllDrives=True
    ).execute()
    
    return file


def update_csv_in_drive(drive, file_id: str, csv_path: Path):
    """Update existing CSV file in Drive"""
    media = MediaFileUpload(
        str(csv_path),
        mimetype='text/csv',
        resumable=True
    )
    
    file = drive.files().update(
        fileId=file_id,
        media_body=media,
        supportsAllDrives=True
    ).execute()
    
    return file


def process_camera(drive, camera_name: str, folder_id: str, local_csv: Path):
    """Process one camera: upload or merge with existing CSV"""
    
    print(f"\nProcessing {camera_name}...")
    
    # Check if CSV already exists in Drive
    existing_file = find_file_in_folder(drive, folder_id, DRIVE_CSV_NAME)
    
    # Load new data
    with open(local_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        new_rows = list(reader)
        fieldnames = reader.fieldnames
    
    if existing_file:
        print(f"  Found existing CSV in Drive (ID: {existing_file['id']})")
        
        # Download existing data
        existing_rows = download_csv_from_drive(drive, existing_file['id'])
        print(f"  Existing rows: {len(existing_rows)}")
        print(f"  New rows: {len(new_rows)}")
        
        # Merge
        merged_rows = merge_csvs(existing_rows, new_rows)
        print(f"  Merged rows: {len(merged_rows)}")
        
        # Write merged data to temp file
        temp_csv = BY_LOCATION_DIR / f"{camera_name}_merged.csv"
        with open(temp_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(merged_rows)
        
        # Update file in Drive
        update_csv_in_drive(drive, existing_file['id'], temp_csv)
        print(f"  ✓ Updated CSV in Drive")
        
        # Clean up temp file
        temp_csv.unlink()
        
    else:
        print(f"  No existing CSV found, creating new file...")
        
        # Upload new file
        upload_csv_to_drive(drive, folder_id, local_csv, DRIVE_CSV_NAME)
        print(f"  ✓ Uploaded new CSV to Drive ({len(new_rows)} rows)")


def main():
    # Check for folder IDs
    if "FOLDER_ID_HERE" in CAMERA_FOLDERS.values():
        print("ERROR: Please update CAMERA_FOLDERS with actual Drive folder IDs")
        print("\nRun this first:")
        print("  python scripts/find_camera_folders.py")
        print("\nThen update CAMERA_FOLDERS in this script with the IDs shown.")
        return
    
    if not BY_LOCATION_DIR.exists():
        raise FileNotFoundError(
            f"{BY_LOCATION_DIR} not found. Run make_output_by_location.py first."
        )
    
    # Authenticate
    print("Authenticating with Google Drive...")
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    drive = build("drive", "v3", credentials=creds)
    
    print("\n" + "=" * 60)
    print("UPLOADING RESULTS TO GOOGLE DRIVE")
    print("=" * 60)
    
    # Process each camera
    for camera_name, folder_id in CAMERA_FOLDERS.items():
        local_csv = BY_LOCATION_DIR / f"{camera_name}_results.csv"
        
        if not local_csv.exists():
            print(f"\n Skipping {camera_name}: no local CSV found")
            continue
        
        try:
            process_camera(drive, camera_name, folder_id, local_csv)
        except Exception as e:
            print(f"\n Error processing {camera_name}: {e}")
            continue
    
    print("\n" + "=" * 60)
    print("✓ UPLOAD COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()