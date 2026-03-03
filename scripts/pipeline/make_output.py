# scripts/pipeline/make_output.py

import csv
import re
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

MANIFEST = Path("data/outputs/manifest.csv")
META = Path("data/outputs/metadata.csv")
DRIVE_INDEX = Path("data/outputs/drive_index.csv")

OUT_DIR = Path("data/outputs/by_location")


def load_csv_by_key(path: Path, key: str) -> dict:
    out = {}
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            k = row.get(key, "")
            if k:
                out[k] = row
    return out


def extract_image_number(filename: str) -> str:
    match = re.search(r'(IMG)_?(\d+)', filename, re.IGNORECASE)
    if match:
        num = match.group(2).zfill(4)
        return f"IMG_{num}"
    return filename


def get_camera_name(drive_row: dict) -> str:
    deployment_folder = (drive_row.get("deployment_folder") or "").strip()
    site = (drive_row.get("site") or "").strip()

    if deployment_folder:
        name = re.sub(r'^\d{4}_\d{2}_\d{2}_', '', deployment_folder)
        name = re.sub(r'_DONE$', '', name)
        if name:
            return name.replace(" ", "")

    return site.replace(" ", "") if site else "Unknown"


def format_date(exif_datetime: str) -> str:
    if not exif_datetime:
        return ""
    try:
        date_part = exif_datetime.split(" ")[0]
        return date_part.replace(":", "")
    except Exception:
        return ""


def format_time(exif_datetime: str) -> str:
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name)
    cleaned = cleaned.strip().strip(".")
    return cleaned or "Unknown"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--metadata", default=str(META))
    parser.add_argument("--drive_index", default=str(DRIVE_INDEX))
    parser.add_argument("--out_dir", default=str(OUT_DIR))
    parser.add_argument("--burst_seconds", type=int, default=300)
    parser.add_argument("--burst_export", choices=["all", "first"], default="all")
    parser.add_argument("--start_date", default="")
    parser.add_argument("--end_date", default="")
    parser.add_argument("--start_time", default="")
    parser.add_argument("--end_time", default="")
    parser.add_argument("--filter_mode", choices=["auto", "md", "speciesnet", "none"], default="auto")
    parser.add_argument("--offset_start_date", default="")
    parser.add_argument("--offset_end_date", default="")
    parser.add_argument("--offset_start_time", default="")
    parser.add_argument("--offset_end_time", default="")
    parser.add_argument("--shift_minutes", type=int, default=0)
    parser.add_argument("--set_year", type=int, default=None)
    parser.add_argument("--set_month", type=int, default=None)
    parser.add_argument("--set_day", type=int, default=None)
    parser.add_argument("--offset_apply_to", choices=["date", "time", "both"], default="both")
    args = parser.parse_args()

    args.burst_seconds = max(10, min(300, int(args.burst_seconds)))

    manifest_path = Path(args.manifest)
    meta_path = Path(args.metadata)
    drive_index_path = Path(args.drive_index)
    out_dir = Path(args.out_dir)

    if not manifest_path.exists():
        raise FileNotFoundError("manifest.csv not found. Run make_manifest.py first.")
    if not meta_path.exists():
        raise FileNotFoundError("metadata.csv not found. Run extract_metadata.py first.")
    if not drive_index_path.exists():
        raise FileNotFoundError("drive_index.csv not found. Run build_index.py first.")

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

    offset_start_date = (args.offset_start_date or "").strip()
    offset_end_date = (args.offset_end_date or "").strip()
    offset_start_time = (args.offset_start_time or "").strip()
    offset_end_time = (args.offset_end_time or "").strip()

    if offset_start_date and not re.match(r"^\d{8}$", offset_start_date):
        raise ValueError("--offset_start_date must be YYYYMMDD (e.g., 20200311)")
    if offset_end_date and not re.match(r"^\d{8}$", offset_end_date):
        raise ValueError("--offset_end_date must be YYYYMMDD (e.g., 20200311)")
    if offset_start_time and not re.match(r"^\d{2}:\d{2}:\d{2}$", offset_start_time):
        raise ValueError("--offset_start_time must be HH:MM:SS (e.g., 13:45:19)")
    if offset_end_time and not re.match(r"^\d{2}:\d{2}:\d{2}$", offset_end_time):
        raise ValueError("--offset_end_time must be HH:MM:SS (e.g., 13:45:19)")

    total_flagged_outside_interval = 0
    total_missing_datetime_for_interval = 0

    rows_by_camera = defaultdict(list)

    total_processed = 0
    total_skipped_blank = 0

    def _normalize_species(val: str) -> str:
        return (val or "").strip().lower()

    def _md_present(mrow: dict) -> bool:
        ha = (mrow.get("has_animal", "") or "").strip()
        hh = (mrow.get("has_human", "") or "").strip()
        return ha in ("0", "1") or hh in ("0", "1")

    def _sn_present(mrow: dict) -> bool:
        sp = _normalize_species(mrow.get("species", "") or "")
        return sp != ""

    def _effective_mode(mrow: dict) -> str:
        if args.filter_mode != "auto":
            return args.filter_mode
        if _md_present(mrow):
            return "md"
        if _sn_present(mrow):
            return "speciesnet"
        return "none"

    def _keep_row(mrow: dict) -> bool:
        mode = _effective_mode(mrow)
        ha = (mrow.get("has_animal", "") or "").strip()
        hh = (mrow.get("has_human", "") or "").strip()
        sp = _normalize_species(mrow.get("species", "") or "")

        if mode == "none":
            return True
        if mode == "md":
            return ha == "1" or hh == "1"
        if mode == "speciesnet":
            return sp not in ("", "blank", "vehicle", "no cv result")
        return True

    def _parse_row_dt(d: str, t: str):
        d = (d or "").strip()
        t = (t or "").strip()
        if not d or not t:
            return None
        if not re.match(r"^\d{8}$", d):
            return None
        if not re.match(r"^\d{2}:\d{2}:\d{2}$", t):
            return None
        try:
            return datetime(
                int(d[0:4]), int(d[4:6]), int(d[6:8]),
                int(t[0:2]), int(t[3:5]), int(t[6:8])
            )
        except Exception:
            return None

    offset_enabled = bool(offset_start_date and offset_end_date) and (
        args.shift_minutes != 0 or args.set_year is not None or args.set_month is not None or args.set_day is not None
    )

    offset_start_dt = None
    offset_end_dt = None
    if offset_enabled:
        try:
            st = offset_start_time if offset_start_time else "00:00:00"
            et = offset_end_time if offset_end_time else "23:59:59"
            offset_start_dt = _parse_row_dt(offset_start_date, st)
            offset_end_dt = _parse_row_dt(offset_end_date, et)
        except Exception:
            offset_start_dt = None
            offset_end_dt = None
        if offset_start_dt is None or offset_end_dt is None:
            offset_enabled = False
        else:
            if offset_end_dt < offset_start_dt:
                offset_enabled = False

    with open(manifest_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            file_id = row["file_id"]
            filename = row["file_name"]

            m = meta_by_id.get(file_id, {})
            d = drive_by_id.get(file_id, {})

            total_processed += 1

            has_animal = (m.get("has_animal", "") or "").strip()
            has_human = (m.get("has_human", "") or "").strip()
            species = (m.get("species", "") or "").strip()
            count = (m.get("count", "") or "").strip()
            model_certainty = (m.get("model_certainty", "") or "").strip()

            sp_norm = species.strip().lower()
            if sp_norm in ("animal", "mammal", "bird", "canis species", "canine family", "rodent", "carnivorous mammal"):
                species = "unknown"

            if not count and species and species.strip().lower() not in ("blank", "vehicle", "no cv result"):
                count = "1"

            if not _keep_row(m):
                total_skipped_blank += 1
                continue

            camera_name = get_camera_name(d)
            deployment_folder = d.get("deployment_folder", "")
            image_num = extract_image_number(filename)

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

            corrected_date = ""
            corrected_time = ""

            if offset_enabled:
                row_dt = _parse_row_dt(date, time_val)
                if row_dt is not None and offset_start_dt is not None and offset_end_dt is not None:
                    if offset_start_dt <= row_dt <= offset_end_dt:
                        new_dt = row_dt
                        try:
                            y = args.set_year if args.set_year is not None else new_dt.year
                            mo = args.set_month if args.set_month is not None else new_dt.month
                            da = args.set_day if args.set_day is not None else new_dt.day
                            new_dt = new_dt.replace(year=y, month=mo, day=da)
                        except Exception:
                            pass

                        if args.shift_minutes != 0:
                            try:
                                new_dt = new_dt + timedelta(minutes=int(args.shift_minutes))
                            except Exception:
                                pass

                        new_date_str = f"{new_dt.year:04d}{new_dt.month:02d}{new_dt.day:02d}"
                        new_time_str = f"{new_dt.hour:02d}:{new_dt.minute:02d}:{new_dt.second:02d}"

                        if args.offset_apply_to == "date":
                            corrected_date = new_date_str
                        elif args.offset_apply_to == "time":
                            corrected_time = new_time_str
                        else:
                            corrected_date = new_date_str
                            corrected_time = new_time_str

                        if args.offset_apply_to == "date":
                            date = corrected_date
                        elif args.offset_apply_to == "time":
                            time_val = corrected_time
                        else:
                            date = corrected_date
                            time_val = corrected_time

                        if notes_val:
                            notes_val = notes_val + "; OFFSET_APPLIED"
                        else:
                            notes_val = "OFFSET_APPLIED"

            row_data = {
                "CameraName": camera_name,
                "DeploymentFolder": deployment_folder,
                "Image#": image_num,
                "Species": species,
                "# of Individuals": count,
                "CorrectedSpecies": "",
                "Corrected# of Individuals": "",
                "HasMultipleSpecies": "",
                "SecondarySpecies": "",
                "Secondary# of Individuals": "",
                "Date": date,
                "Time": time_val,
                "CorrectedDate": corrected_date,
                "CorrectedTime": corrected_time,
                "ObservationID": "",
                "BurstCount": "",
                "BurstIndex": "",
                "has_animal": has_animal,
                "has_human": has_human,
                "model_certainty": model_certainty,
                "Notes": notes_val,
            }

            rows_by_camera[camera_name].append(row_data)

    FINAL_FIELDS = [
        "CameraName",
        "DeploymentFolder",
        "Image#",
        "Species",
        "# of Individuals",
        "CorrectedSpecies",
        "Corrected# of Individuals",
        "HasMultipleSpecies",
        "SecondarySpecies",
        "Secondary# of Individuals",
        "Date",
        "Time",
        "CorrectedDate",
        "CorrectedTime",
        "ObservationID",
        "BurstCount",
        "BurstIndex",
        "has_animal",
        "has_human",
        "model_certainty",
        "Notes",
    ]

    out_dir.mkdir(parents=True, exist_ok=True)

    total_output = 0
    export_rows = []

    for camera_name, rows in sorted(rows_by_camera.items()):
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
                if not re.match(r"^\d{8}$", d):
                    return None
                try:
                    dt = datetime(
                        int(d[0:4]), int(d[4:6]), int(d[6:8]),
                        int(m.group(1)), int(m.group(2)), int(m.group(3))
                    )
                    return int((dt - datetime(1970, 1, 1)).total_seconds())
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

                mode = _effective_mode({
                    "has_animal": burst_rows[0].get("has_animal", ""),
                    "has_human": burst_rows[0].get("has_human", ""),
                    "species": burst_rows[0].get("Species", ""),
                })

                keep_ok = True
                if mode == "md":
                    ha = (burst_rows[0].get("has_animal", "") or "").strip()
                    hh = (burst_rows[0].get("has_human", "") or "").strip()
                    keep_ok = (ha == "1" or hh == "1")
                elif mode == "speciesnet":
                    sp = _normalize_species(burst_rows[0].get("Species", "") or "")
                    keep_ok = sp not in ("", "blank", "vehicle", "no cv result")
                elif mode == "none":
                    keep_ok = True

                if keep_ok:
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
                mode = _effective_mode({
                    "has_animal": r.get("has_animal", ""),
                    "has_human": r.get("has_human", ""),
                    "species": r.get("Species", ""),
                })

                keep_ok = True
                if mode == "md":
                    ha = (r.get("has_animal", "") or "").strip()
                    hh = (r.get("has_human", "") or "").strip()
                    keep_ok = (ha == "1" or hh == "1")
                elif mode == "speciesnet":
                    sp = _normalize_species(r.get("Species", "") or "")
                    keep_ok = sp not in ("", "blank", "vehicle", "no cv result")
                elif mode == "none":
                    keep_ok = True

                if keep_ok:
                    if first_kept_in_burst is not None and args.burst_export != "all":
                        pass
                    if first_kept_in_burst is None:
                        first_kept_in_burst = r
                    if args.burst_export == "all":
                        kept_rows.append(r)

            if args.burst_export == "first" and first_kept_in_burst is not None:
                kept_rows.append(first_kept_in_burst)

            i = j

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