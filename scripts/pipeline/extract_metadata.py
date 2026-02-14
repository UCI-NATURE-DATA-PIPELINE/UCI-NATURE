# reads manifest.csv and extracts EXIF datetime + image width/height for each local file.
# Adds ML output columns by merging data/outputs/ml_outputs.csv (if present)
# Supports: has_animal, has_human, species, count, model_certainty

import csv
from pathlib import Path
from PIL import Image
import exifread

MANIFEST = Path("data/outputs/manifest.csv")
OUT_CSV = Path("data/outputs/metadata.csv")
ML_OUT = Path("data/outputs/ml_outputs.csv")  # optional


def get_exif_datetime(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False)
        for key in ("EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime"):
            if key in tags:
                return str(tags[key])
    except Exception:
        return ""
    return ""


def split_date_time(dt_str: str):
    if not dt_str:
        return "", ""
    try:
        date_part, time_part = dt_str.split(" ", 1)
        return date_part.replace(":", ""), time_part  # YYYYMMDD, HH:MM:SS
    except Exception:
        return "", ""


def get_size(path: Path):
    try:
        with Image.open(path) as img:
            return img.width, img.height
    except Exception:
        return "", ""


def load_ml_by_id(path: Path) -> dict:
    if not path.exists():
        return {}
    out = {}
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fid = row.get("file_id", "")
            if fid:
                out[fid] = row
    return out


def to_flag01(val):
    s = str(val).strip()
    if s == "":
        return ""
    try:
        return "1" if int(float(s)) == 1 else "0"
    except Exception:
        return ""


def main():
    if not MANIFEST.exists():
        raise FileNotFoundError("manifest.csv not found. Run download and make_manifest first.")

    ml_by_id = load_ml_by_id(ML_OUT)

    rows_out = []
    with open(MANIFEST, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            file_id = row["file_id"]
            path = Path(row["local_path"])

            exif_dt = get_exif_datetime(path)
            date, time = split_date_time(exif_dt)
            w, h = get_size(path)

            ml = ml_by_id.get(file_id, {})
            has_animal = to_flag01(ml.get("has_animal", ""))
            has_human = to_flag01(ml.get("has_human", ""))

            is_blank = ""
            if has_animal != "" and has_human != "":
                is_blank = "1" if (has_animal == "0" and has_human == "0") else "0"

            rows_out.append({
                "file_id": file_id,
                "file_name": row["file_name"],
                "local_file_name": row["local_file_name"],

                "exif_datetime": exif_dt,
                "date": date,
                "time": time,

                "width": w,
                "height": h,

                # ML (filled if ml_outputs.csv exists)
                "has_animal": has_animal,
                "has_human": has_human,
                "is_blank": is_blank,
                "species": ml.get("species", ""),
                "count": ml.get("count", ""),
                "model_certainty": ml.get("model_certainty", ""),
            })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "file_id", "file_name", "local_file_name",
        "exif_datetime", "date", "time",
        "width", "height",
        "has_animal", "has_human", "is_blank", "species", "count", "model_certainty"
    ]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_out)

    print(f"wrote {len(rows_out)} rows -> {OUT_CSV}")
    if not ML_OUT.exists():
        print("Note: ml_outputs.csv not found, ML columns left blank.")


if __name__ == "__main__":
    main()