# Merges manifest, metadata, and drive_index into final output CSVs
# Creates one CSV per camera location (ResearchPark.csv, BonitaCanyon1.csv, etc.)
#
# IMPORTANT: Only includes rows where an animal OR human was detected.
# Blank images (no detection) and vehicle-only images are excluded from output.
# This matches Julie's existing spreadsheet format.

import csv
import re
import argparse
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


def safe_filename(name: str) -> str:
    # keep it simple: remove characters that break filenames
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name)
    cleaned = cleaned.strip().strip(".")
    return cleaned or "Unknown"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--metadata", default=str(META))
    parser.add_argument("--drive_index", default=str(DRIVE_INDEX))
    parser.add_argument("--out_dir", default=str(OUT_DIR))
    parser.add_argument("--burst_seconds", type=int, default=5)
    parser.add_argument("--burst_export", choices=["all", "first"], default="all")
    parser.add_argument("--start_date", default="")
    parser.add_argument("--end_date", default="")
    parser.add_argument("--start_time", default="")
    parser.add_argument("--end_time", default="")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    meta_path = Path(args.metadata)
    drive_index_path = Path(args.drive_index)
    out_dir = Path(args.out_dir)

    # Check required files exist
    if not manifest_path.exists():
        raise FileNotFoundError("manifest.csv not found. Run make_manifest.py first.")
    if not meta_path.exists():
        raise FileNotFoundError("metadata.csv not found. Run extract_metadata.py first.")
    if not drive_index_path.exists():
        raise FileNotFoundError("drive_index.csv not found. Run build_index.py first.")

    # Load data
    meta_by_id = load_csv_by_key(meta_path, "file_id")
    drive_by_id = load_csv_by_key(drive_index_path, "file_id")

    start_date = (args.start_date or "").strip()
    end_date = (args.end_date or "").strip()
    start_time = (args.start_time or "").strip()
    end_time = (args.end_time or "").strip()

    if start_date and not re.match(r"^\d{8}$", start_date):
        raise ValueError("--start_date must be YYYYMMDD (e.g., 20200311)")
    if end_date and not re.match(r"^\d{8}$", end_date):
        raise ValueError("--end_date must be YYYYMMDD (e.g., 20200311)")
    if start_time and not re.match(r"^\d{2}:\d{2}:\d{2}$", start_time):
        raise ValueError("--start_time must be HH:MM:SS (e.g., 13:45:19)")
    if end_time and not re.match(r"^\d{2}:\d{2}:\d{2}$", end_time):
        raise ValueError("--end_time must be HH:MM:SS (e.g., 13:45:19)")

    total_flagged_outside_interval = 0
    total_missing_datetime_for_interval = 0

    # Group rows by camera location
    rows_by_camera = defaultdict(list)

    total_processed = 0
    total_skipped_blank = 0

    with open(manifest_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            file_id = row["file_id"]
            filename = row["file_name"]

            m = meta_by_id.get(file_id, {})
            d = drive_by_id.get(file_id, {})

            total_processed += 1

            # Get ML outputs
            has_animal = (m.get("has_animal", "") or "").strip()
            has_human = (m.get("has_human", "") or "").strip()
            species = (m.get("species", "") or "").strip()
            count = (m.get("count", "") or "").strip()
            model_certainty = (m.get("model_certainty", "") or "").strip()

            is_animal = has_animal == "1"
            is_human = has_human == "1"
            if not is_animal and not is_human:
                total_skipped_blank += 1

            # Extract metadata
            camera_name = get_camera_name(d)
            deployment_folder = d.get("deployment_folder", "")
            image_num = extract_image_number(filename)

            # Prefer metadata.csv date/time (already standardized), fallback to exif_datetime if needed
            date = (m.get("date", "") or "").strip()
            time_val = (m.get("time", "") or "").strip()

            if not date or not time_val:
                exif_dt = (m.get("exif_datetime", "") or "").strip()
                if not date:
                    date = format_date(exif_dt)
                if not time_val:
                    time_val = format_time(exif_dt)

            notes_val = ""

            if (start_date or end_date or start_time or end_time):
                if not date or not time_val:
                    total_missing_datetime_for_interval += 1
                    notes_val = "WARNING: Missing date/time for interval check"
                else:
                    outside = False

                    if start_date and date < start_date:
                        outside = True
                    if end_date and date > end_date:
                        outside = True

                    if start_date and end_date and start_date == end_date:
                        if start_time and time_val < start_time:
                            outside = True
                        if end_time and time_val > end_time:
                            outside = True
                    else:
                        if start_date and date == start_date and start_time and time_val < start_time:
                            outside = True
                        if end_date and date == end_date and end_time and time_val > end_time:
                            outside = True

                    if outside:
                        total_flagged_outside_interval += 1
                        notes_val = "WARNING: Date/time outside deployment interval"

            row_data = {
                "CameraName": camera_name,
                "DeploymentFolder": deployment_folder,
                "Image#": image_num,
                "Species": species,
                "# of Individuals": count,
                "Date": date,
                "Time": time_val,
                "ObservationID": "",
                "BurstCount": "",
                "BurstIndex": "",
                "has_animal": has_animal,
                "has_human": has_human,
                "model_certainty": model_certainty,
                "Notes": notes_val,
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
        "ObservationID",
        "BurstCount",
        "BurstIndex",
        "has_animal",
        "has_human",
        "model_certainty",
        "Notes",
    ]

    # Write one CSV per camera location
    out_dir.mkdir(parents=True, exist_ok=True)

    total_output = 0
    export_rows = []

    for camera_name, rows in sorted(rows_by_camera.items()):
        # Sort rows by date, time
        rows.sort(key=lambda r: (r.get("Date", ""), r.get("Time", "")))

        obs_seq = 0
        i = 0
        kept_rows = []

        while i < len(rows):
            def _to_seconds(r: dict) -> int | None:
                d = (r.get("Date", "") or "").strip()
                t = (r.get("Time", "") or "").strip()
                if not d or not t:
                    return None
                m = re.match(r"^(\d{2}):(\d{2}):(\d{2})$", t)
                if not m:
                    return None
                try:
                    y = int(d[0:4])
                    mo = int(d[4:6])
                    da = int(d[6:8])
                    hh = int(m.group(1))
                    mm = int(m.group(2))
                    ss = int(m.group(3))
                    return (((y * 12 + mo) * 31 + da) * 24 + hh) * 3600 + mm * 60 + ss
                except Exception:
                    return None

            start = i
            start_sec = _to_seconds(rows[i])

            if start_sec is None:
                obs_seq += 1
                burst_rows = rows[i:i+1]
                obs_id_date = (burst_rows[0].get("Date", "") or "").strip()
                obs_id = f"{camera_name}_{obs_id_date}_{str(obs_seq).zfill(6)}"
                burst_rows[0]["ObservationID"] = obs_id
                burst_rows[0]["BurstCount"] = "1"
                burst_rows[0]["BurstIndex"] = "1"

                has_animal = (burst_rows[0].get("has_animal", "") or "").strip()
                has_human = (burst_rows[0].get("has_human", "") or "").strip()
                is_animal = has_animal == "1"
                is_human = has_human == "1"
                if is_animal or is_human:
                    kept_rows.append(burst_rows[0])

                i += 1
                continue

            j = i + 1
            prev_sec = start_sec
            while j < len(rows):
                cur_sec = _to_seconds(rows[j])
                if cur_sec is None:
                    break
                if cur_sec - prev_sec <= args.burst_seconds:
                    prev_sec = cur_sec
                    j += 1
                else:
                    break

            obs_seq += 1
            burst_rows = rows[start:j]
            burst_count = len(burst_rows)
            obs_id_date = (burst_rows[0].get("Date", "") or "").strip()
            obs_id = f"{camera_name}_{obs_id_date}_{str(obs_seq).zfill(6)}"

            for idx_in_burst, r in enumerate(burst_rows, start=1):
                r["ObservationID"] = obs_id
                r["BurstCount"] = str(burst_count)
                r["BurstIndex"] = str(idx_in_burst)

            first_kept_in_burst = None
            for r in burst_rows:
                has_animal = (r.get("has_animal", "") or "").strip()
                has_human = (r.get("has_human", "") or "").strip()
                is_animal = has_animal == "1"
                is_human = has_human == "1"
                if is_animal or is_human:
                    if first_kept_in_burst is None:
                        first_kept_in_burst = r
                    if args.burst_export == "all":
                        kept_rows.append(r)

            if args.burst_export == "first" and first_kept_in_burst is not None:
                kept_rows.append(first_kept_in_burst)

            i = j

        # Write CSV for this camera
        csv_path = out_dir / f"{safe_filename(camera_name)}.csv"
        write_csv(csv_path, kept_rows, FINAL_FIELDS)

        total_output += len(kept_rows)
        export_rows.extend(kept_rows)
        print(f"  {camera_name}: {len(kept_rows)} images -> {csv_path}")

    animal_count = sum(1 for r in export_rows if (r.get("has_animal", "") or "").strip() == "1")
    human_only_count = sum(1 for r in export_rows if (r.get("has_human", "") or "").strip() == "1")
    species_filled = sum(1 for r in export_rows if (r.get("Species", "") or "").strip() != "")

    print(f"\nTotal: {total_output} images across {len(rows_by_camera)} locations")
    print(f"Output directory: {out_dir}")

    if (start_date or end_date or start_time or end_time):
        print(f"\nInterval checks:")
        print(f"  Flagged outside interval: {total_flagged_outside_interval}")
        print(f"  Missing date/time for check: {total_missing_datetime_for_interval}")

    print(f"\nFiltering:")
    print(f"  Total images processed: {total_processed}")
    print(f"  Kept (animal or human): {total_output}")
    print(f"    Animals: {animal_count}")
    print(f"    Humans (by Species=human): {human_only_count}")
    print(f"  Skipped (blank/vehicle): {total_skipped_blank}")

    print(f"\nColumns filled automatically:")
    print("  ✓ CameraName (from folder structure)")
    print("  ✓ DeploymentFolder (SD card upload identifier)")
    print("  ✓ Image# (from filename)")
    print("  ✓ Date (from EXIF metadata)")
    print("  ✓ Time (from EXIF metadata)")

    print(f"\nMegaDetector results:")
    print(f"  ✓ has_animal — {animal_count} animals")
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