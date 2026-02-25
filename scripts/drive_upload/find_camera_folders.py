"""
Finds camera folder IDs in Julie's Wildlife Database on Google Drive.
This helps us know where to upload the processed CSV files.
"""

from google.oauth2 import service_account
from googleapiclient.discovery import build
from pathlib import Path

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


def list_folders(drive, parent_id, indent=0):
    """Recursively list folders and their IDs"""
    query = f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    
    results = drive.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    
    folders = results.get('files', [])
    
    camera_folders = {}
    
    for folder in folders:
        name = folder['name']
        folder_id = folder['id']
        
        prefix = "  " * indent
        print(f"{prefix}📁 {name}")
        print(f"{prefix}   ID: {folder_id}")
        
        # Check if this is a camera folder
        if name in CAMERA_NAMES:
            camera_folders[name] = folder_id
            print(f"{prefix}   ⭐ CAMERA FOLDER")
        
        # Recurse into subfolders (limit depth to avoid going too deep)
        if indent < 2:
            sub_cameras = list_folders(drive, folder_id, indent + 1)
            camera_folders.update(sub_cameras)
    
    return camera_folders


def main():
    print("=" * 60)
    print("FINDING CAMERA FOLDERS IN GOOGLE DRIVE")
    print("=" * 60)
    print()
    
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    drive = build("drive", "v3", credentials=creds)
    
    print("Scanning Wildlife Camera Photo Database...\n")
    
    camera_folders = list_folders(drive, ROOT_FOLDER_ID)
    
    print("\n" + "=" * 60)
    print("CAMERA FOLDER MAPPING")
    print("=" * 60)
    
    if camera_folders:
        print("\nFound these camera folders:\n")
        for name, folder_id in camera_folders.items():
            print(f'  "{name}": "{folder_id}",')
        
        print("\n Copy this mapping to use in upload script!")
    else:
        print("\n No camera folders found!")
        print("Looking for:", CAMERA_NAMES)
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()