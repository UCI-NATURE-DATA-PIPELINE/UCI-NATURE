# Merges manifest, metadata, and drive_index into final output CSVs
# Creates one CSV per camera location (ResearchPark.csv, BonitaCanyon1.csv, etc.)
#
# IMPORTANT: Only includes rows where an animal OR human was detected.
# Blank images (no detection) and vehicle-only images are excluded from output.
# This matches Julie's existing spreadsheet format.

import csv
import re
from pathlib import Path
from collections import defaultdict

MANIFEST = Path("data/outputs/manifest.csv")
META = Path("data/outputs/metadata.csv")
DRIVE_INDEX = Path("data/outputs/drive_index.csv")

OUT_DIR = Path("data/outputs/by_location")


def load_csv_by_key(path: Path, key: str) -> dict:
    """Load CSV into dict keyed by specified column."""
    out = {}
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            k = row.get(key, "")
            if k:
                out[k] = row
    return out


def extract_image_number(filename: str) -> str:
    """
    Extract image number from filename.
    Examples:
      RESPARK_20200429_IMG0001.JPG -> IMG_0001
      IMG_0042.JPG -> IMG_0042
      BonitaCanyon1_IMG0123.JPG -> IMG_0123
    """
    match = re.search(r'(IMG)_?(\d+)', filename, re.IGNORECASE)
    if match:
        num = match.group(2).zfill(4)
        return f"IMG_{num}"
    return filename


def get_camera_name(drive_row: dict) -> str:
    """
    Extract camera name from drive folder structure.
    Examples:
      Research Park/2020_05_01_ResPark/... -> ResearchPark
      Bonita Canyon/BonitaCanyon1/... -> BonitaCanyon1
      Bonita Canyon/2020_09_17_BonitaCanyon2/... -> BonitaCanyon2
    """
    deployment_folder = (drive_row.get("deployment_folder") or "").strip()
    site = (drive_row.get("site") or "").strip()

    # Try to extract camera name from deployment folder
    if deployment_folder:
        # Remove date prefix like "2020_05_01_"
        name = re.sub(r'^\d{4}_\d{2}_\d{2}_', '', deployment_folder)
        # Remove _DONE suffix
        name = re.sub(r'_DONE$', '', name)
        if name:
            return name.replace(" ", "")

    # Fall back to site name, remove spaces
    return site.replace(" ", "") if site else "Unknown"


def format_date(exif_datetime: str) -> str:
    """
    Convert EXIF datetime to YYYYMMDD format.
    Input: "2020:05:01 11:55:28"
    Output: "20200501"
    """
    if not exif_datetime:
        return ""
    try:
        date_part = exif_datetime.split(" ")[0]
        return date_part.replace(":", "")
    except Exception:
        return ""


def format_time(exif_datetime: str) -> str:
    """
    Convert EXIF datetime to HH:MM:SS format.
    Input: "2020:05:01 11:55:28"
    Output: "11:55:28"
    """
    if not exif_datetime:
        return ""
    try:
        parts = exif_datetime.split(" ")
        if len(parts) > 1:
            return parts[1]
    except Exception:
        pass
    return ""


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    """Write rows to CSV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    # Check required files exist
    if not MANIFEST.exists():
        raise FileNotFoundError("manifest.csv not found. Run make_manifest.py first.")
    if not META.exists():
        raise FileNotFoundError("metadata.csv not found. Run extract_metadata.py first.")
    if not DRIVE_INDEX.exists():
        raise FileNotFoundError("drive_index.csv not found. Run build_index.py first.")

    # Load data
    meta_by_id = load_csv_by_key(META, "file_id")
    drive_by_id = load_csv_by_key(DRIVE_INDEX, "file_id")

    # Group rows by camera location
    rows_by_camera = defaultdict(list)

    total_processed = 0
    total_skipped_blank = 0

    with open(MANIFEST, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            file_id = row["file_id"]
            filename = row["file_name"]

            m = meta_by_id.get(file_id, {})
            d = drive_by_id.get(file_id, {})

            total_processed += 1

            # Get ML outputs
            has_animal = m.get("has_animal", "")
            has_human = m.get("has_human", "")
            species = m.get("species", "")
            count = m.get("count", "")
            model_certainty = m.get("model_certainty", "")

            # FILTER: Only include rows with animal or human detected
            # Skip blank images (no detection) and vehicle-only images
            is_animal = str(has_animal).strip() == "1"
            is_human = str(has_human).strip() == "1"

            if not is_animal and not is_human:
                total_skipped_blank += 1
                continue

            # Extract metadata
            camera_name = get_camera_name(d)
            deployment_folder = d.get("deployment_folder", "")
            image_num = extract_image_number(filename)

            exif_dt = m.get("exif_datetime", "")
            date = format_date(exif_dt)
            time = format_time(exif_dt)

            row_data = {
                "CameraName": camera_name,
                "DeploymentFolder": deployment_folder,
                "Image#": image_num,
                "Species": species,
                "# of Individuals": count,
                "Date": date,
                "Time": time,
                "has_animal": has_animal,
                "model_certainty": model_certainty,
                "Notes": "",
            }

            # Group by camera name
            rows_by_camera[camera_name].append(row_data)

    # Define column order
    FINAL_FIELDS = [
        "CameraName",
        "DeploymentFolder",
        "Image#",
        "Species",
        "# of Individuals",
        "Date",
        "Time",
        "has_animal",
        "model_certainty",
        "Notes",
    ]

    # Write one CSV per camera location
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    total_output = 0
    for camera_name, rows in sorted(rows_by_camera.items()):
        # Sort rows by date, time
        rows.sort(key=lambda r: (r.get("Date", ""), r.get("Time", "")))

        # Write CSV for this camera
        csv_path = OUT_DIR / f"{camera_name}.csv"
        write_csv(csv_path, rows, FINAL_FIELDS)

        total_output += len(rows)
        print(f"  {camera_name}: {len(rows)} images -> {csv_path}")

    # Count what's actually in the output
    all_rows = [r for rows in rows_by_camera.values() for r in rows]
    animal_count = sum(1 for r in all_rows if str(r.get("has_animal", "")) == "1")
    human_count = sum(1 for r in all_rows if str(r.get("has_animal", "")) == "0")
    species_filled = sum(1 for r in all_rows if r.get("Species", "") != "")

    print(f"\nTotal: {total_output} images across {len(rows_by_camera)} locations")
    print(f"Output directory: {OUT_DIR}")

    print(f"\nFiltering:")
    print(f"  Total images processed: {total_processed}")
    print(f"  Kept (animal or human): {total_output}")
    print(f"    Animals: {animal_count}")
    print(f"    Humans: {human_count}")
    print(f"  Skipped (blank/vehicle): {total_skipped_blank}")

    print(f"\nColumns filled automatically:")
    print("  ✓ CameraName (from folder structure)")
    print("  ✓ DeploymentFolder (SD card upload identifier)")
    print("  ✓ Image# (from filename)")
    print("  ✓ Date (from EXIF metadata)")
    print("  ✓ Time (from EXIF metadata)")

    print(f"\nMegaDetector results:")
    print(f"  ✓ has_animal — {animal_count} animals, {human_count} humans")
    print(f"  ✓ model_certainty — confidence scores filled")
    print(f"  ✓ # of Individuals — detection counts filled")

    if species_filled > 0:
        print(f"\nSpeciesNet results:")
        print(f"  ✓ Species — {species_filled}/{total_output} classified")
    else:
        print(f"\nSpecies classification:")
        print("  ○ Species (run SpeciesNet to fill this column)")

    print(f"\nManual columns:")
    print("  ○ Notes (human review)")


if __name__ == "__main__":
    main()