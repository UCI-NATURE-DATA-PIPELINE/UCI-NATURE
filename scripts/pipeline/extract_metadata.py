# Converts SpeciesNet output into a simple per-image CSV keyed by file_id.
#
# SpeciesNet runs MegaDetector internally, so speciesnet_results.json contains:
#   - detections: animal/person/vehicle (same categories as MegaDetector)
#   - prediction: species classification with geofencing
#   - prediction_score: confidence
#
# Species labels are simplified to match Julie's spreadsheet format:
#   coyote, rabbit, raccoon, squirrel, bird, opossum, skunk, bobcat, human, etc.
#
# Only images with animal or human detections are kept. Blanks/vehicles are filtered out.
# scripts/pipeline/extract_metadata.py
import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ExifTags

OUT_CSV_DEFAULT = Path("data/outputs/metadata.csv")
ML_OUT_DEFAULT = Path("data/outputs/ml_outputs.csv")

_EXIF_TAGS = {v: k for k, v in ExifTags.TAGS.items()}


def _get_exif_datetime_pillow(img: Image.Image) -> str:
    try:
        exif = img.getexif()
        if not exif:
            return ""
        for tag_name in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
            tag_id = _EXIF_TAGS.get(tag_name)
            if tag_id is None:
                continue
            val = exif.get(tag_id)
            if val:
                return str(val)
    except Exception:
        return ""
    return ""


def _split_date_time(exif_dt: str) -> tuple[str, str]:
    if not exif_dt:
        return "", ""
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(exif_dt.strip(), fmt)
            return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S")
        except Exception:
            pass
    s = exif_dt.strip()
    if " " in s:
        d, t = s.split(" ", 1)
        return d.replace(":", "-"), t
    return s.replace(":", "-"), ""


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def load_ml_outputs(path: Path) -> tuple[dict[str, dict[str, str]], list[str]]:
    if not path.exists():
        return {}, []
    out: dict[str, dict[str, str]] = {}
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        for r in reader:
            fid = (r.get("file_id") or r.get("fileId") or r.get("id") or "").strip()
            if fid:
                out[fid] = {k: (r.get(k, "") or "") for k in fields}
    return out, fields


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract EXIF datetime and image dimensions for each manifest row.")
    ap.add_argument("--manifest", required=True, help="Path to manifest.csv")
    ap.add_argument("--out", default=str(OUT_CSV_DEFAULT), help="Output metadata CSV path")
    ap.add_argument("--ml_outputs", default=str(ML_OUT_DEFAULT), help="Optional ML outputs CSV to merge (keyed by file_id)")
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    out_path = Path(args.out)
    ml_path = Path(args.ml_outputs)

    manifest_rows = read_csv(manifest_path)
    ml_map, ml_fields = load_ml_outputs(ml_path)

    base_fields = ["file_id", "file_name", "local_file_name", "local_path", "size_bytes", "modified_time"]
    out_fields = base_fields + ["exif_datetime", "date", "time", "width", "height"]

    if ml_map:
        for k in ml_fields:
            if k not in out_fields:
                out_fields.append(k)

    out_rows: list[dict[str, Any]] = []

    for r in manifest_rows:
        file_id = (r.get("file_id", "") or "").strip()
        local_path = (r.get("local_path", "") or "").strip()

        exif_dt = ""
        width = ""
        height = ""

        if local_path:
            p = Path(local_path)
            if p.exists():
                try:
                    with Image.open(p) as img:
                        exif_dt = _get_exif_datetime_pillow(img)
                        width, height = str(img.size[0]), str(img.size[1])
                except Exception:
                    exif_dt = ""
                    width = ""
                    height = ""

        date_s, time_s = _split_date_time(exif_dt)

        row_out: dict[str, Any] = {k: (r.get(k, "") or "") for k in base_fields}
        row_out["file_id"] = file_id
        row_out["local_path"] = local_path
        row_out.update(
            {
                "exif_datetime": exif_dt,
                "date": date_s,
                "time": time_s,
                "width": width,
                "height": height,
            }
        )

        if file_id and file_id in ml_map:
            for k, v in ml_map[file_id].items():
                if k not in row_out:
                    row_out[k] = v

        out_rows.append(row_out)

    write_csv(out_path, out_rows, out_fields)


if __name__ == "__main__":
    main()