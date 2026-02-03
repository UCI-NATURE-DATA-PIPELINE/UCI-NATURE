# Converts model outputs into a simple per-image CSV keyed by file_id.
# Current implementation supports MegaDetector-style JSON (common format).
# If md_results.json is missing, this script creates an empty ml_outputs.csv so the pipeline can continue.

import csv
import json
from pathlib import Path

MANIFEST = Path("data/outputs/manifest.csv")

# Put your detector output here (generated separately by MegaDetector)
MD_RESULTS_JSON = Path("data/outputs/md_results.json")

OUT_ML = Path("data/outputs/ml_outputs.csv")

# category mapping (MegaDetector convention):
# 1 = animal, 2 = person, 3 = vehicle
ANIMAL_CATEGORY = {"1", 1}
DEFAULT_THRESHOLD = 0.5


def load_manifest_index():
    """Build indices to match MegaDetector 'file' entries back to our file_id."""
    by_local_path = {}
    by_basename = {}

    if not MANIFEST.exists():
        return by_local_path, by_basename

    with open(MANIFEST, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fid = row.get("file_id", "")
            lp = row.get("local_path", "")
            bn = Path(lp).name if lp else row.get("local_file_name", "")
            if fid:
                if lp:
                    by_local_path[lp] = fid
                if bn:
                    by_basename[bn] = fid
    return by_local_path, by_basename


def find_file_id(md_file: str, by_local_path: dict, by_basename: dict):
    if not md_file:
        return ""
    if md_file in by_local_path:
        return by_local_path[md_file]
    bn = Path(md_file).name
    return by_basename.get(bn, "")


def main():
    OUT_ML.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["file_id", "has_animal", "species", "count", "model_certainty"]

    by_local_path, by_basename = load_manifest_index()

    if not MD_RESULTS_JSON.exists():
        with open(OUT_ML, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
        print(f"md_results.json not found -> wrote empty {OUT_ML} (ML columns will remain blank).")
        return

    with open(MD_RESULTS_JSON, "r", encoding="utf-8") as f:
        md = json.load(f)

    images = md.get("images", [])
    rows = []

    for img in images:
        md_file = img.get("file") or img.get("filename") or ""
        fid = find_file_id(md_file, by_local_path, by_basename)
        if not fid:
            continue

        dets = img.get("detections") or []
        animal_confs = []
        animal_count = 0

        for det in dets:
            cat = det.get("category")
            conf = det.get("conf")
            if conf is None:
                continue
            try:
                conf_f = float(conf)
            except Exception:
                continue
            if cat in ANIMAL_CATEGORY:
                animal_confs.append(conf_f)
                if conf_f >= DEFAULT_THRESHOLD:
                    animal_count += 1

        max_animal_conf = max(animal_confs) if animal_confs else 0.0
        has_animal = 1 if max_animal_conf >= DEFAULT_THRESHOLD else 0

        rows.append({
            "file_id": fid,
            "has_animal": has_animal,
            "species": "",  # future work
            "count": animal_count if has_animal else 0,
            "model_certainty": round(max_animal_conf, 4),
        })

    # Deduplicate by file_id (keep last)
    dedup = {r["file_id"]: r for r in rows}

    with open(OUT_ML, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(dedup.values())

    print(f"wrote {len(dedup)} rows -> {OUT_ML}")


if __name__ == "__main__":
    main()
