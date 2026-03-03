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
# Only images with animals or humans are kept (blank + vehicle removed).
#
# Output: data/outputs/speciesnet_results.csv
#
# Columns:
#   file_id, file_name, local_path,
#   has_animal, has_human, is_vehicle,
#   species, model_certainty, count (optional), burst_id/burst_size optional

import json
import csv
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime

RESULTS_JSON = Path("data/outputs/speciesnet_results.json")
OUT_CSV = Path("data/outputs/speciesnet_results.csv")
OUT_JSON = Path("data/outputs/speciesnet_results_post.json")
MANIFEST = Path("data/outputs/manifest.csv")

DEFAULT_BURST_WINDOW = 300

# Normalize some common SpeciesNet labels
SPECIES_MAP = {
    "canis latrans": "coyote",
    "oryctolagus cuniculus": "rabbit",
    "procyon lotor": "raccoon",
    "sciurus": "squirrel",
    "didelphis virginiana": "opossum",
    "mephitis mephitis": "skunk",
    "lynx rufus": "bobcat",
    "homo sapiens": "human",
    "bird": "bird",
}

# These are spreadsheet-friendly output labels (priority order)
LABELS_PRIORITY = [
    "human",
    "coyote",
    "bobcat",
    "raccoon",
    "opossum",
    "skunk",
    "rabbit",
    "squirrel",
    "bird",
]

DET_LABEL_MAP = {
    "animal": "animal",
    "person": "human",
    "vehicle": "vehicle",
}

def safe_float(x):
    try:
        return float(x)
    except Exception:
        return 0.0

def simplify_species(label: str) -> str:
    if not label:
        return ""
    lab = label.strip().lower()
    if lab in SPECIES_MAP:
        return SPECIES_MAP[lab]
    # fuzzy contains
    for k, v in SPECIES_MAP.items():
        if k in lab:
            return v
    return lab

def parse_exif_datetime(s: str):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return int(dt.timestamp())
        except Exception:
            pass
    return None

def read_manifest(path: Path):
    """Return dict[file_id] -> {file_name, local_path, exif_datetime/modified_time}"""
    out = {}
    if not path.exists():
        return out
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            fid = r.get("file_id", "") or ""
            if not fid:
                continue
            out[fid] = r
    return out

def burst_group(rows, window_s: int):
    """rows = list of (file_id, ts_int) sorted by time; returns dict[burst_id] -> list[file_ids]"""
    if not rows:
        return {}
    rows = sorted(rows, key=lambda x: x[1])
    groups = defaultdict(list)
    burst_id = 1
    start_t = rows[0][1]
    prev_t = rows[0][1]
    groups[burst_id].append(rows[0][0])
    for fid, ts in rows[1:]:
        if ts - prev_t <= window_s and ts - start_t <= window_s:
            groups[burst_id].append(fid)
        else:
            burst_id += 1
            start_t = ts
            groups[burst_id].append(fid)
        prev_t = ts
    return groups

def pick_burst_rep(file_ids, mode: str):
    if not file_ids:
        return ""
    if mode == "first":
        return file_ids[0]
    if mode == "last":
        return file_ids[-1]
    if mode == "middle":
        return file_ids[len(file_ids)//2]
    return ""

def choose_label(species_candidates, dets):
    """Return (label, conf) for this image using MD category + species predictions."""
    best_det = ""
    best_det_conf = 0.0
    for d in (dets or []):
        cat = (d.get("category") or "").strip().lower()
        conf = safe_float(d.get("conf") or d.get("confidence") or 0.0)
        cat_norm = DET_LABEL_MAP.get(cat, "")
        if cat_norm and conf > best_det_conf:
            best_det = cat_norm
            best_det_conf = conf

    best_sp = ""
    best_sp_conf = 0.0
    for lab, sc in (species_candidates or []):
        lab_s = simplify_species(lab)
        if sc > best_sp_conf:
            best_sp = lab_s
            best_sp_conf = sc

    # If MD says person/vehicle, trust it
    if best_det == "human":
        return "human", best_det_conf
    if best_det == "vehicle":
        return "vehicle", best_det_conf

    # If MD says animal, use species if present
    if best_det == "animal":
        if best_sp:
            return best_sp, best_sp_conf
        return "animal", best_det_conf

    # otherwise fallback
    if best_sp:
        return best_sp, best_sp_conf
    return best_det, best_det_conf

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results_json", default=str(RESULTS_JSON))
    ap.add_argument("--manifest", default=str(MANIFEST))
    ap.add_argument("--out_csv", default=str(OUT_CSV))
    ap.add_argument("--out_json", default=str(OUT_JSON))
    ap.add_argument("--burst_window", type=int, default=DEFAULT_BURST_WINDOW)
    ap.add_argument("--burst_export", default="all", choices=["all", "first", "middle", "last"])
    args = ap.parse_args()

    results_path = Path(args.results_json)
    manifest_path = Path(args.manifest)
    out_csv = Path(args.out_csv)
    out_json = Path(args.out_json)

    manifest = read_manifest(manifest_path)

    raw = json.loads(results_path.read_text(encoding="utf-8"))
    images = raw.get("images") if isinstance(raw, dict) else raw
    if not isinstance(images, list):
        raise SystemExit("speciesnet_results.json unexpected format")

    per_image = {}

    for img in images:
        file_id = img.get("file_id") or img.get("fileId") or img.get("id") or ""
        if not file_id:
            continue

        dets = img.get("detections") or img.get("dets") or []
        preds = img.get("predictions") or img.get("prediction") or []

        species_candidates = []
        for p in (preds or []):
            lab = p.get("label") or p.get("species") or ""
            sc = safe_float(p.get("score") or p.get("prediction_score") or p.get("conf") or p.get("confidence") or 0.0)
            if lab:
                species_candidates.append((lab, sc))

        label, conf = choose_label(species_candidates, dets)

        has_human = 1 if label == "human" else 0
        is_vehicle = 1 if label == "vehicle" else 0
        has_animal = 1 if (label and label not in ("human", "vehicle")) else 0

        per_image[file_id] = {
            "file_id": file_id,
            "label": label,
            "confidence": conf,
            "has_animal": has_animal,
            "has_human": has_human,
            "is_vehicle": is_vehicle,
            "detections": dets,
            "predictions": preds,
        }

    # Burst grouping (optional) using manifest timestamps if available
    rows_for_burst = []
    for fid in per_image.keys():
        mrow = manifest.get(fid, {})
        exif_dt = mrow.get("exif_datetime", "") or ""
        mod_dt = mrow.get("modified_time", "") or ""
        ts = parse_exif_datetime(exif_dt) or parse_exif_datetime(mod_dt)
        if ts is not None:
            rows_for_burst.append((fid, ts))

    groups = burst_group(rows_for_burst, args.burst_window)

    burst_id_for = {}
    burst_size_for = {}
    for gid, fids in groups.items():
        for fid in fids:
            burst_id_for[fid] = gid
            burst_size_for[fid] = len(fids)

    export_keep = set()
    if args.burst_export != "all":
        for gid, fids in groups.items():
            rep = pick_burst_rep(fids, args.burst_export)
            if rep:
                export_keep.add(rep)

    out_rows = []
    for fid, info in per_image.items():
        mrow = manifest.get(fid, {})
        file_name = mrow.get("file_name", "") or ""
        local_path = mrow.get("local_path", "") or ""

        burst_id = burst_id_for.get(fid, 0)
        burst_size = burst_size_for.get(fid, 1)

        keep = 1
        if args.burst_export != "all":
            keep = 1 if fid in export_keep else 0

        out_rows.append({
            "file_id": fid,
            "file_name": file_name,
            "local_path": local_path,
            "has_animal": info.get("has_animal", 0),
            "has_human": info.get("has_human", 0),
            "is_vehicle": info.get("is_vehicle", 0),
            "species": info.get("label", ""),
            "model_certainty": info.get("confidence", 0.0),
            "burst_id": burst_id,
            "burst_size": burst_size,
            "burst_keep": keep,
        })

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "file_id",
        "file_name",
        "local_path",
        "has_animal",
        "has_human",
        "is_vehicle",
        "species",
        "model_certainty",
        "burst_id",
        "burst_size",
        "burst_keep",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps({"images": per_image, "bursts": groups}, indent=2), encoding="utf-8")

    print(f"wrote {len(out_rows)} rows -> {out_csv}")
    print(f"wrote -> {out_json}")

if __name__ == "__main__":
    main()