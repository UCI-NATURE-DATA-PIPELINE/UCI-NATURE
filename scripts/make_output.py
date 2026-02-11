# Merges all data sources into final output.csv
# Fixed: Proper column mapping and encoding

import csv
from pathlib import Path
from datetime import datetime

MANIFEST = Path("data/outputs/manifest.csv")
META = Path("data/outputs/metadata.csv")
DRIVE_INDEX = Path("data/outputs/drive_index.csv")

OUT_FINAL = Path("data/outputs/output.csv")

FINAL_COLUMNS = [
    "image_id", "camera_name", "date", "time",
    "has_animal", "is_blank", "species", "count", "model_certainty",
]


def load_csv_by_key(path: Path, key: str) -> dict:
    out = {}
    if not path.exists():
        return out
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            k = row.get(key, "")
            if k:
                out[k] = row
    return out


def parse_drive_datetime(dt: str) -> tuple:
    if not dt:
        return "", ""
    try:
        s = dt.replace("Z", "")
        t = datetime.fromisoformat(s)
        return t.date().isoformat(), t.time().replace(microsecond=0).isoformat()
    except Exception:
        try:
            date_part = dt.split("T", 1)[0]
            time_part = dt.split("T", 1)[1].split(".", 1)[0].replace("Z", "")
            return date_part, time_part
        except Exception:
            return "", ""


def get_camera_name(drive_data: dict) -> str:
    site = (drive_data.get("site") or "").strip()
    drive_path = (drive_data.get("drive_path") or "").strip()

    if site and not site.lower().startswith("old"):
        return site

    if drive_path:
        parts = drive_path.split("/")
        if parts and parts[0].lower().startswith("old") and len(parts) > 1:
            return parts[1]
        return parts[0] if parts else ""
    
    return site


def main():
    OUT_FINAL.parent.mkdir(parents=True, exist_ok=True)
    
    print("Starting final output generation...")
    
    if not MANIFEST.exists():
        raise FileNotFoundError(f"manifest.csv not found at {MANIFEST}")
    if not DRIVE_INDEX.exists():
        raise FileNotFoundError(f"drive_index.csv not found at {DRIVE_INDEX}")
    
    # Load data
    meta_by_id = load_csv_by_key(META, "file_id") if META.exists() else {}
    drive_by_id = load_csv_by_key(DRIVE_INDEX, "file_id")
    
    print(f"Loaded metadata for {len(meta_by_id)} files")
    print(f"Loaded drive index for {len(drive_by_id)} files")
    
    final_rows = []
    stats = {"total": 0, "with_datetime": 0, "with_ml": 0, "animals": 0, "blanks": 0}
    
    with open(MANIFEST, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            stats["total"] += 1
            file_id = row["file_id"]
            
            meta = meta_by_id.get(file_id, {})
            drive = drive_by_id.get(file_id, {})
            
            camera_name = get_camera_name(drive)
            
            # Get date/time from metadata or drive
            date = (meta.get("date") or "").strip()
            time_val = (meta.get("time") or "").strip()
            
            if not date or not time_val:
                d_date, d_time = parse_drive_datetime(drive.get("modifiedTime", ""))
                date = date or d_date
                time_val = time_val or d_time
            
            if date and time_val:
                stats["with_datetime"] += 1
            
            # ML columns
            has_animal = (meta.get("has_animal") or "").strip()
            is_blank = (meta.get("is_blank") or "").strip()
            
            if has_animal != "":
                stats["with_ml"] += 1
                if has_animal == "1":
                    stats["animals"] += 1
                if is_blank == "1":
                    stats["blanks"] += 1
            
            final_rows.append({
                "image_id": file_id,
                "camera_name": camera_name,
                "date": date,
                "time": time_val,
                "has_animal": has_animal,
                "is_blank": is_blank,
                "species": (meta.get("species") or "").strip(),
                "count": (meta.get("count") or "").strip(),
                "model_certainty": (meta.get("model_certainty") or "").strip(),
            })
    
    # Write output
    with open(OUT_FINAL, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FINAL_COLUMNS)
        w.writeheader()
        w.writerows(final_rows)
    
    print(f"\n" + "=" * 50)
    print(f"FINAL OUTPUT GENERATED: {OUT_FINAL}")
    print(f"=" * 50)
    print(f"Total rows: {stats['total']}")
    print(f"With date/time: {stats['with_datetime']}")
    print(f"With ML results: {stats['with_ml']}")
    print(f"  Animals: {stats['animals']}, Blanks: {stats['blanks']}")


if __name__ == "__main__":
    main()
