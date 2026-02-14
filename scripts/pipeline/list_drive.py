# lists files inside the test folder using a service account

from google.oauth2 import service_account
from googleapiclient.discovery import build

# config 
SERVICE_ACCOUNT_FILE = "secrets/inf191a-uci-nature-sa.json"   # key file for service account auth
FOLDER_ID = "0ACQBvZlfUN2CUk9PVA"               # drive folder to pull from 
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]    # read only access


def main():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    drive = build("drive", "v3", credentials=creds)

    query = f"'{FOLDER_ID}' in parents and trashed = false"
    res = drive.files().list(
        q=query,
        fields="files(id,name,mimeType,size,modifiedTime)",
        pageSize=1000,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()

    files = res.get("files", [])
    print(f"found {len(files)} files")
    for f in files[:50]:
        print(f"{f['name']} | {f['id']} | {f.get('mimeType')}")

if __name__ == "__main__":
    main()
