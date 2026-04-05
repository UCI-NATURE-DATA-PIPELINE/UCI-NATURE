from typing import Optional
import argparse
import csv
import io
import re
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from scripts.config import SERVICE_ACCOUNT_FILE


BY_LOCATION_DIR = Path("data/outputs/by_location")
DRIVE_INDEX = Path("data/outputs/drive_index.csv")
DRIVE_CSV_NAME = "wildlife_results.csv"

FIELDNAMES = [
    "CameraName",
    "DeploymentFolder",
    "Image#",
    "Species",
    "# of Individuals",
    "CorrectedSpecies",
    "Corrected# of Individuals",
    "Date",
    "Time",
    "Notes",
]

SHEETS_MIME = "application/vnd.google-apps.spreadsheet"


def normalize_camera_name(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^\d{4}_\d{2}_\d{2}_", "", value)
    value = re.sub(r"_DONE$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"_results$", "", value, flags=re.IGNORECASE)
    value = value.replace(" ", "")
    return value


def load_legacy_camera_folders(mapping_csv: Path) -> dict[str, str]:
    mapping_csv = Path(mapping_csv)
    if not mapping_csv.exists():
        raise FileNotFoundError(f"Missing legacy mapping file: {mapping_csv}")

    mapping: dict[str, str] = {}
    with open(mapping_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            camera_name = normalize_camera_name(row.get("camera_name", ""))
            folder_id = (row.get("folder_id") or "").strip()
            if not camera_name or not folder_id:
                continue
            mapping[camera_name] = folder_id

    if not mapping:
        raise ValueError(f"Legacy mapping file is empty or invalid: {mapping_csv}")

    return mapping


def build_camera_deployment_map(drive_index_path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    drive_index_path = Path(drive_index_path)

    if not drive_index_path.exists():
        return mapping

    with open(drive_index_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            deployment = (row.get("deployment_folder") or "").strip()
            folder_id = (row.get("drive_folder_id") or "").strip()
            if not deployment or not folder_id:
                continue

            camera_name = normalize_camera_name(deployment)
            if camera_name and camera_name not in mapping:
                mapping[camera_name] = folder_id

    return mapping


def get_parent_folder_id(drive, folder_id: str) -> Optional[str]:
    try:
        result = drive.files().get(
            fileId=folder_id,
            fields="parents",
            supportsAllDrives=True,
        ).execute()
        parents = result.get("parents", [])
        return parents[0] if parents else None
    except HttpError:
        return None


def resolve_dynamic_camera_folders(drive, drive_index_path: Path) -> dict[str, str]:
    deployment_map = build_camera_deployment_map(drive_index_path)
    if not deployment_map:
        return {}

    parent_cache: dict[str, str] = {}
    camera_folders: dict[str, str] = {}

    for camera_name, deployment_folder_id in deployment_map.items():
        if deployment_folder_id not in parent_cache:
            parent_id = get_parent_folder_id(drive, deployment_folder_id)
            if parent_id:
                parent_cache[deployment_folder_id] = parent_id

        resolved_folder_id = parent_cache.get(deployment_folder_id)
        if resolved_folder_id:
            camera_folders[camera_name] = resolved_folder_id

    return camera_folders


def load_csv_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_csv_bytes(rows: list[dict]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDNAMES, extrasaction="ignore")
    writer.writeheader()

    for row in rows:
        normalized_row = {key: row.get(key, "") for key in FIELDNAMES}
        writer.writerow(normalized_row)

    return output.getvalue().encode("utf-8")


def find_file_in_folder(drive, folder_id: str, filename: str):
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    results = drive.files().list(
        q=query,
        fields="files(id, name, mimeType)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = results.get("files", [])
    return files[0] if files else None


def create_csv_in_drive(
    drive,
    folder_id: str,
    filename: str,
    rows: list[dict],
    as_sheet: bool = True,
):
    content = to_csv_bytes(rows)
    file_metadata = {
        "name": filename,
        "parents": [folder_id],
    }
    if as_sheet:
        file_metadata["mimeType"] = SHEETS_MIME

    media = MediaIoBaseUpload(
        io.BytesIO(content),
        mimetype="text/csv",
        resumable=False,
    )

    return drive.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name, mimeType",
        supportsAllDrives=True,
    ).execute()


def overwrite_csv_in_drive(
    drive,
    file_id: str,
    rows: list[dict],
    file_mime: str = "text/csv",
):
    content = to_csv_bytes(rows)
    media = MediaIoBaseUpload(
        io.BytesIO(content),
        mimetype="text/csv",
        resumable=False,
    )

    body = {}
    if file_mime == SHEETS_MIME:
        body["mimeType"] = SHEETS_MIME

    return drive.files().update(
        fileId=file_id,
        body=body,
        media_body=media,
        fields="id, name, mimeType",
        supportsAllDrives=True,
    ).execute()


def _row_key(row: dict) -> str:
    image_num = (row.get("Image#") or "").strip()
    deployment = (row.get("DeploymentFolder") or "").strip()
    species = (row.get("Species") or "").strip()

    if image_num:
        return "|".join([deployment, image_num, species])

    return ""


def append_rows_to_drive_csv(
    drive,
    file_id: str,
    new_rows: list[dict],
    file_mime: str = "text/csv",
):
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
    existing_text = buf.read().decode("utf-8", errors="replace")
    existing_rows = list(csv.DictReader(io.StringIO(existing_text)))

    existing_keys = {_row_key(row) for row in existing_rows if _row_key(row)}
    rows_to_add = [row for row in new_rows if _row_key(row) and _row_key(row) not in existing_keys]

    merged_rows = existing_rows + rows_to_add
    overwrite_csv_in_drive(drive, file_id, merged_rows, file_mime=file_mime)

    return {
        "existing_rows": len(existing_rows),
        "appended_rows": len(rows_to_add),
        "final_rows": len(merged_rows),
    }


def process_camera(
    drive,
    camera_name: str,
    folder_id: str,
    local_csv: Path,
    overwrite: bool = False,
    as_sheet: bool = True,
):
    print(f"\nProcessing {camera_name}")
    print(f"  Local CSV: {local_csv}")
    print(f"  Drive folder: {folder_id}")

    rows = load_csv_rows(local_csv)
    if not rows:
        print("  Skipping: local CSV is empty")
        return False

    existing_file = find_file_in_folder(drive, folder_id, DRIVE_CSV_NAME)

    if existing_file:
        print(f"  Found existing file: {existing_file['name']}")
        if overwrite:
            overwrite_csv_in_drive(
                drive,
                existing_file["id"],
                rows,
                file_mime=existing_file.get("mimeType", "text/csv"),
            )
            print("  Overwrote existing file")
        else:
            result = append_rows_to_drive_csv(
                drive,
                existing_file["id"],
                rows,
                file_mime=existing_file.get("mimeType", "text/csv"),
            )
            print(
                f"  Appended {result['appended_rows']} new rows "
                f"({result['existing_rows']} existing, {result['final_rows']} total)"
            )
    else:
        create_csv_in_drive(
            drive,
            folder_id,
            DRIVE_CSV_NAME,
            rows,
            as_sheet=as_sheet,
        )
        print("  Created new file")

    return True


def find_local_csv_for_camera(camera_name: str) -> Optional[Path]:
    normalized_target = normalize_camera_name(camera_name)

    preferred = BY_LOCATION_DIR / f"{camera_name}_results.csv"
    if preferred.exists():
        return preferred

    for local_csv in sorted(BY_LOCATION_DIR.glob("*.csv")):
        if normalize_camera_name(local_csv.stem) == normalized_target:
            return local_csv

    return None


def iter_legacy_targets(legacy_map_path: Path):
    camera_folders = load_legacy_camera_folders(legacy_map_path)

    for camera_name, folder_id in camera_folders.items():
        local_csv = find_local_csv_for_camera(camera_name)
        if not local_csv:
            print(f"\nSkipping {camera_name}: no local CSV found")
            continue
        yield camera_name, folder_id, local_csv


def iter_dynamic_targets(drive, drive_index_path: Path):
    camera_folders = resolve_dynamic_camera_folders(drive, drive_index_path)
    if not camera_folders:
        print("WARNING: drive_index.csv not found or empty, or no matching parent folders were resolved.")
        return

    for local_csv in sorted(BY_LOCATION_DIR.glob("*.csv")):
        camera_name = normalize_camera_name(local_csv.stem)
        folder_id = camera_folders.get(camera_name)

        if not folder_id:
            print(f"\nSkipping {camera_name}: no matching Drive folder found in drive_index.csv")
            continue

        yield camera_name, folder_id, local_csv


def main():
    parser = argparse.ArgumentParser(description="Upload output CSVs to Google Drive.")
    parser.add_argument(
        "--mode",
        choices=["legacy", "dynamic"],
        default="legacy",
        help="legacy uses a provided camera-folder mapping file, dynamic resolves folders from drive_index.csv",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite existing Drive file instead of appending new rows",
    )
    parser.add_argument(
        "--drive-index",
        default=str(DRIVE_INDEX),
        help="path to drive_index.csv for dynamic mode",
    )
    parser.add_argument(
        "--legacy-map",
        default="",
        help="path to csv file with columns camera_name,folder_id for legacy mode",
    )
    parser.add_argument(
        "--as-csv",
        action="store_true",
        help="create new Drive files as CSV instead of Google Sheets",
    )
    args = parser.parse_args()

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    drive = build("drive", "v3", credentials=creds)

    print("\n" + "=" * 60)
    print("UPLOADING RESULTS TO GOOGLE DRIVE")
    print("=" * 60)
    print(f"Mode: {args.mode}")

    if args.mode == "legacy":
        if not args.legacy_map:
            raise ValueError("legacy mode requires --legacy-map")
        targets = iter_legacy_targets(Path(args.legacy_map))
    else:
        targets = iter_dynamic_targets(drive, Path(args.drive_index))

    processed = 0
    for camera_name, folder_id, local_csv in targets:
        try:
            did_process = process_camera(
                drive=drive,
                camera_name=camera_name,
                folder_id=folder_id,
                local_csv=local_csv,
                overwrite=args.overwrite,
                as_sheet=not args.as_csv,
            )
            if did_process:
                processed += 1
        except HttpError as e:
            print(f"\nError processing {camera_name}: {e}")
            continue
        except Exception as e:
            print(f"\nError processing {camera_name}: {e}")
            continue

    print("\n" + "=" * 60)
    print("UPLOAD COMPLETE")
    print(f"Processed {processed} camera CSV file(s).")
    print("=" * 60)


if __name__ == "__main__":
    main()