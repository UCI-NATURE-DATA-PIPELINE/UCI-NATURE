"""
Finds camera folder IDs in Julie's Wildlife Database on Google Drive.
FIXED: Only scans 1 level deep - no more recursing into image folders.
"""

from google.oauth2 import service_account
from googleapiclient.discovery import build

SERVICE_ACCOUNT_FILE = "secrets/inf191a-uci-nature-sa.json"
ROOT_FOLDER_ID = "0ACQBvZlfUN2CUk9PVA"  # Wildlife Camera Photo Database
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

CAMERA_NAMES = [
    "Research Park",
    "Bonita Canyon1",
    "Bonita Canyon2",
    "Marshtrail",
    "OLD Locations (Deprecated Cameras)"
]


def list_top_level_folders(drive, parent_id):
    """List ONLY direct children folders - no recursion"""
    query = f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"

    results = drive.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()

    return results.get('files', [])


def main():
    print("=" * 60)
    print("FINDING CAMERA FOLDERS IN GOOGLE DRIVE")
    print("=" * 60)

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    drive = build("drive", "v3", credentials=creds)

    print("\nScanning top-level folders only...\n")

    # Level 1: top-level folders inside root
    top_folders = list_top_level_folders(drive, ROOT_FOLDER_ID)
    print(f"Found {len(top_folders)} top-level folders:\n")

    camera_folders = {}

    for folder in top_folders:
        name = folder['name']
        folder_id = folder['id']
        print(f" {name}  |  {folder_id}")

        if name in CAMERA_NAMES:
            camera_folders[name] = folder_id
            print(f" CAMERA FOLDER FOUND")

        # Only go one level deeper for OLD Locations
        if name == "OLD Locations (Deprecated Cameras)":
            sub = list_top_level_folders(drive, folder_id)
            for sf in sub:
                print(f"     📁 {sf['name']}  |  {sf['id']}")
                if sf['name'] in CAMERA_NAMES:
                    camera_folders[sf['name']] = sf['id']

    print("\n" + "=" * 60)
    print("CAMERA FOLDER MAPPING")
    print("=" * 60)

    if camera_folders:
        print("\nCopy this into upload_to_drive.py:\n")
        print("CAMERA_FOLDERS = {")
        for name, fid in camera_folders.items():
            safe_name = name.replace(" ", "_")
            print(f'    "{safe_name}": "{fid}",')
        print("}")
    else:
        print("\nNo camera folders found at top level.")
        print("They may be nested deeper - check Drive manually.")

    print("=" * 60)


if __name__ == "__main__":
    main()