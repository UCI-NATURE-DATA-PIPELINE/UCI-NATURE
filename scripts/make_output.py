import csv
from pathlib import Path
from datetime import datetime

MANIFEST = Path("data/outputs/manifest.csv")
META = Path("data/outputs/metadata.csv")
DRIVE_INDEX = Path("data/outputs/drive_index.csv")

OUT_FINAL = Path("data/outputs/output.csv")


def load_csv_by_key(path: Path, key: str) -> dict:
    out = {}
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            k = row.get(key, "")
            if k:
                out[k] = row
    return out


def parse_drive_datetime(dt: str):
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


def get_camera_name(d: dict) -> str:
    site = (d.get("site") or "").strip()
    drive_path = (d.get("drive_path") or "").strip()

    if site and not site.lower().startswith("old"):
        return site

    if drive_path:
        parts = drive_path.split("/")
        if parts and parts[0].lower().startswith("old") and len(parts) > 1:
            return parts[1]
        return parts[0] if parts else ""
    return site


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    if not MANIFEST.exists():
        raise FileNotFoundError("manifest.csv not found. Run make_manifest.py first.")
    if not META.exists():
        raise FileNotFoundError("metadata.csv not found. Run extract_metadata.py first.")
    if not DRIVE_INDEX.exists():
        raise FileNotFoundError("drive_index.csv not found. Run build_index.py first.")

    meta_by_id = load_csv_by_key(META, "file_id")
    drive_by_id = load_csv_by_key(DRIVE_INDEX, "file_id")

    final_rows = []
    with open(MANIFEST, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            file_id = row["file_id"]
            m = meta_by_id.get(file_id, {})
            d = drive_by_id.get(file_id, {})

            camera_name = get_camera_name(d)

            date = (m.get("date") or "").strip()
            time = (m.get("time") or "").strip()
            if not date or not time:
                d_date, d_time = parse_drive_datetime(d.get("modifiedTime", ""))
                date = date or d_date
                time = time or d_time

            final_rows.append({
                "image_id": file_id,
                "camera_name": camera_name,
                "date": date,
                "time": time,
                "has_animal": (m.get("has_animal") or "").strip(),
                "species": (m.get("species") or "").strip(),
                "count": (m.get("count") or "").strip(),
                "model_certainty": (m.get("model_certainty") or "").strip(),
            })

    FINAL_FIELDS = [
        "image_id","camera_name","date","time",
        "has_animal","species","count","model_certainty"
    ]
    write_csv(OUT_FINAL, final_rows, FINAL_FIELDS)
    print(f"wrote {len(final_rows)} rows -> {OUT_FINAL}")


if __name__ == "__main__":
    main()
