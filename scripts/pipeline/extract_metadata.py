# scripts/pipeline/extract_metadata.py

import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from PIL import ExifTags, Image
except ImportError:
    ExifTags = None
    Image = None


OUT_CSV_DEFAULT = Path("data/outputs/metadata.csv")
ML_OUT_DEFAULT = Path("data/outputs/ml_outputs.csv")

_EXIF_TAGS = {v: k for k, v in ExifTags.TAGS.items()} if ExifTags else {}


def _get_exif_datetime_pillow(img) -> str:
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


def merge_metadata_with_ml_outputs(metadata_path: Path, ml_path: Path) -> dict[str, Any]:
    metadata_path = Path(metadata_path)
    ml_path = Path(ml_path)

    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata CSV not found: {metadata_path}")

    metadata_rows = read_csv(metadata_path)
    ml_map, ml_fields = load_ml_outputs(ml_path)

    if not metadata_rows:
        return {
            "metadata_path": str(metadata_path),
            "rows_written": 0,
            "ml_fields_merged": len(ml_fields),
        }

    fieldnames = list(metadata_rows[0].keys())
    for field in ml_fields:
        if field not in fieldnames:
            fieldnames.append(field)

    out_rows = []
    for row in metadata_rows:
        out = dict(row)
        fid = (row.get("file_id") or "").strip()
        for field in ml_fields:
            out.setdefault(field, "")
        if fid and fid in ml_map:
            for k, v in ml_map[fid].items():
                out[k] = v
        out_rows.append(out)

    write_csv(metadata_path, out_rows, fieldnames)

    return {
        "metadata_path": str(metadata_path),
        "rows_written": len(out_rows),
        "ml_fields_merged": len(ml_fields),
    }


def extract_metadata_from_manifest(
    manifest_path: Path,
    out_path: Path = OUT_CSV_DEFAULT,
    ml_path: Path = ML_OUT_DEFAULT,
    merge_ml: bool = True,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    out_path = Path(out_path)
    ml_path = Path(ml_path)

    manifest_rows = read_csv(manifest_path)
    ml_map, ml_fields = ({}, [])
    if merge_ml:
        ml_map, ml_fields = load_ml_outputs(ml_path)

    base_fields = [
        "file_id",
        "file_name",
        "local_file_name",
        "local_path",
        "size_bytes",
        "modified_time",
    ]
    out_fields = base_fields + [
        "exif_datetime",
        "datetime",
        "date",
        "time",
        "width",
        "height",
    ]

    for field in ml_fields:
        if field not in out_fields:
            out_fields.append(field)

    out_rows: list[dict[str, Any]] = []

    for r in manifest_rows:
        file_id = (r.get("file_id", "") or "").strip()
        local_path = (r.get("local_path", "") or "").strip()

        exif_dt = ""
        width = ""
        height = ""

        if local_path:
            p = Path(local_path)
            if p.exists() and Image is not None:
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
                "datetime": f"{date_s} {time_s}".strip() if date_s or time_s else "",
                "date": date_s,
                "time": time_s,
                "width": width,
                "height": height,
            }
        )

        for k in ml_fields:
            row_out[k] = ""

        if file_id and file_id in ml_map:
            for k, v in ml_map[file_id].items():
                row_out[k] = v

        out_rows.append(row_out)

    write_csv(out_path, out_rows, out_fields)

    return {
        "manifest_path": str(manifest_path),
        "metadata_path": str(out_path),
        "rows_written": len(out_rows),
        "ml_fields_merged": len(ml_fields),
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Extract EXIF datetime and image dimensions for each manifest row."
    )
    ap.add_argument("--manifest", required=True, help="Path to manifest.csv")
    ap.add_argument(
        "--out",
        default=str(OUT_CSV_DEFAULT),
        help="Output metadata CSV path",
    )
    ap.add_argument(
        "--ml_outputs",
        default=str(ML_OUT_DEFAULT),
        help="Optional ML outputs CSV to merge (keyed by file_id)",
    )
    ap.add_argument(
        "--no_merge_ml",
        action="store_true",
        help="Do not merge ML outputs during metadata extraction",
    )
    args = ap.parse_args()

    extract_metadata_from_manifest(
        manifest_path=Path(args.manifest),
        out_path=Path(args.out),
        ml_path=Path(args.ml_outputs),
        merge_ml=not args.no_merge_ml,
    )


if __name__ == "__main__":
    main()