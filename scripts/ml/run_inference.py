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

import argparse
import csv
import json
from pathlib import Path

MANIFEST = Path("data/outputs/manifest.csv")
SPECIESNET_JSON = Path("data/outputs/speciesnet_results.json")
MEGADETECTOR_JSON = Path("data/outputs/md_results.json")
OUT_ML = Path("data/outputs/ml_outputs.csv")

LOG_DIR = Path("data/outputs/logs")
UNMATCHED_CSV = LOG_DIR / "unmatched_predictions.csv"
SUMMARY_JSON = LOG_DIR / "ml_summary.json"

# SpeciesNet uses MegaDetector detection categories:
# "1" = animal, "2" = human, "3" = vehicle
ANIMAL_CATEGORY = {"1", "animal"}
PERSON_CATEGORY = {"2", "human"}
DEFAULT_THRESHOLD = 0.5

# ============================================================
# SPECIES LABEL MAPPING
# Maps SpeciesNet taxonomy terms to Julie's simple labels.
# SpeciesNet prediction format: "uuid;class;order;family;genus;species;common_name"
# We check common_name, genus, family, and order against these mappings.
#
# To add a new species: add a line like  "taxonomy_term": "simple_label",
# The taxonomy_term should be lowercase and can match any field in the prediction.
# ============================================================

SPECIES_MAP = {
    # Canids
    "coyote": "coyote",
    "canis latrans": "coyote",
    "domestic dog": "domestic dog",
    "canis lupus familiaris": "domestic dog",
    "gray fox": "gray fox",
    "urocyon cinereoargenteus": "gray fox",

    # Felids
    "bobcat": "bobcat",
    "lynx rufus": "bobcat",
    "domestic cat": "domestic cat",
    "felis catus": "domestic cat",

    # Rabbits
    "rabbit": "rabbit",
    "sylvilagus": "rabbit",
    "sylvilagus bachmani": "rabbit",
    "sylvilagus audubonii": "rabbit",
    "brush rabbit": "rabbit",
    "desert cottontail": "rabbit",
    "leporidae": "rabbit",
    "eastern cottontail": "rabbit",

    # Squirrels
    "squirrel": "squirrel",
    "sciuridae": "squirrel",
    "sciuridae family": "squirrel",
    "sciurus": "squirrel",
    "sciurus niger": "squirrel",
    "eastern fox squirrel": "squirrel",
    "eastern gray squirrel": "squirrel",
    "sciurus carolinensis": "squirrel",
    "otospermophilus": "squirrel",
    "otospermophilus beecheyi": "squirrel",
    "california ground squirrel": "squirrel",
    "rock squirrel": "squirrel",

    # Raccoons
    "raccoon": "raccoon",
    "procyon": "raccoon",
    "procyon lotor": "raccoon",
    "northern raccoon": "raccoon",

    # Opossums
    "opossum": "opossum",
    "didelphis": "opossum",
    "didelphis virginiana": "opossum",
    "virginia opossum": "opossum",

    # Skunks
    "skunk": "skunk",
    "mephitis": "skunk",
    "mephitis mephitis": "skunk",
    "striped skunk": "skunk",

    # Deer
    "deer": "deer",
    "odocoileus": "deer",
    "odocoileus hemionus": "deer",
    "mule deer": "deer",
    "odocoileus virginianus": "deer",
    "white-tailed deer": "deer",

    # Woodrats
    "woodrat": "woodrat",
    "neotoma": "woodrat",

    # Birds
    "bird": "bird",
    "aves": "bird",

    # Rodents (generic fallback)
    "rodentia": "rodent",
    "mammalia": "unknown mammal",

    # Humans & vehicles
    "homo sapiens": "human",
    "human": "human",
    "vehicle": "vehicle",
    "car": "car",
    "bike": "bike",
}


def parse_species_label(prediction_str: str) -> str:
    """
    Parse SpeciesNet prediction string and return a simple species label.

    Format: "uuid;class;order;family;genus;species;common_name"
    Example: "e4d1e892-...;mammalia;rodentia;sciuridae;;;sciuridae family"

    Checks common_name first, then species, genus, family, order, class
    against SPECIES_MAP. Returns the first match.
    """
    if not prediction_str or not isinstance(prediction_str, str):
        return ""

    parts = prediction_str.split(";")
    # Expected: uuid;class;order;family;genus;species;common_name
    # Guard against short/odd strings
    while len(parts) < 7:
        parts.append("")

    uuid, cls, order, family, genus, species, common = [p.strip().lower() for p in parts[:7]]

    # Check from most specific to least
    for key in (common, species, genus, family, order, cls):
        if key and key in SPECIES_MAP:
            return SPECIES_MAP[key]

    # Fallback: if it's a human label in any field
    if "human" in (common, species, genus, family, order, cls):
        return "human"

    return "unknown"


def _read_manifest_index_by_local_name(manifest_path: Path) -> dict[str, dict]:
    """
    Returns a mapping of local_file_name -> manifest row dict.
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    out: dict[str, dict] = {}
    with open(manifest_path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            local_name = (row.get("local_file_name") or "").strip()
            if local_name:
                out[local_name] = row
    return out


def _safe_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _max_detection_conf(detections: list[dict], categories: set[str], threshold: float) -> float:
    best = 0.0
    for det in detections or []:
        cat = str(det.get("category", "")).lower()
        conf = _safe_float(det.get("conf", det.get("confidence", 0.0)), 0.0)
        if cat in categories and conf >= threshold and conf > best:
            best = conf
    return best


def run_speciesnet(manifest_csv: Path, speciesnet_json: Path, out_csv: Path, threshold: float) -> None:
    if not speciesnet_json.exists():
        raise FileNotFoundError(f"SpeciesNet results not found: {speciesnet_json}")

    manifest_by_local = _read_manifest_index_by_local_name(manifest_csv)

    with open(speciesnet_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    predictions = data.get("predictions", []) or []

    rows = []
    unmatched = []
    blank_or_vehicle = 0

    for pred in predictions:
        local_name = (pred.get("file") or pred.get("file_name") or "").strip()
        if not local_name:
            # SpeciesNet sometimes stores full path; take basename
            local_name = Path(pred.get("filepath", "")).name if pred.get("filepath") else ""
        local_name = Path(local_name).name

        manifest_row = manifest_by_local.get(local_name)
        if not manifest_row:
            unmatched.append({
                "provider": "speciesnet",
                "pred_file": local_name,
            })
            continue

        detections = pred.get("detections") or []
        has_animal_conf = _max_detection_conf(detections, ANIMAL_CATEGORY, threshold)
        has_human_conf = _max_detection_conf(detections, PERSON_CATEGORY, threshold)

        has_animal = 1 if has_animal_conf > 0 else 0
        has_human = 1 if (has_human_conf > 0) else 0

        # Write blanks/vehicles to ml_outputs.csv so extract_metadata can propagate
        # has_animal=0 into metadata.csv, allowing make_output.py to filter them out.
        if has_animal == 0 and has_human == 0:
            blank_or_vehicle += 1
            rows.append({
                "file_id": manifest_row.get("file_id", ""),
                "local_file_name": manifest_row.get("local_file_name", ""),
                "local_path": manifest_row.get("local_path", ""),
                "has_animal": 0,
                "has_human": 0,
                "species": "blank",
                "model_certainty": "",
            })
            continue

        prediction_str = pred.get("prediction", "")
        species = parse_species_label(prediction_str)

        # If it's human-only, force species=human (keeps consistency)
        if has_animal == 0 and has_human == 1:
            species = "human"

        model_certainty = _safe_float(pred.get("prediction_score", pred.get("score", 0.0)), 0.0)

        rows.append({
            "file_id": manifest_row.get("file_id", ""),
            "local_file_name": manifest_row.get("local_file_name", ""),
            "local_path": manifest_row.get("local_path", ""),
            "has_animal": has_animal,
            "has_human": has_human,
            "species": species,
            "model_certainty": model_certainty,
        })

    # Deduplicate by file_id (keep the best certainty)
    dedup = {}
    for row in rows:
        fid = row.get("file_id", "")
        if not fid:
            continue
        if fid not in dedup:
            dedup[fid] = row
        else:
            if _safe_float(row.get("model_certainty", 0.0)) > _safe_float(dedup[fid].get("model_certainty", 0.0)):
                dedup[fid] = row

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["file_id", "local_file_name", "local_path", "has_animal", "has_human", "species", "model_certainty"]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(dedup.values())

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(UNMATCHED_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["provider", "pred_file"])
        w.writeheader()
        w.writerows(unmatched)

    summary = {
        "provider": "speciesnet",
        "total_predictions_in_json": len(predictions),
        "matched_to_manifest": len(predictions) - len(unmatched),
        "unmatched_to_manifest": len(unmatched),
        "with_animal_or_human": animal_rows + human_rows,
        "blank_or_vehicle": blank_or_vehicle,
        "threshold": threshold,
        "out_csv": str(out_csv),
        "unmatched_csv": str(UNMATCHED_CSV),
    }
    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Summary
    total_input = len(predictions)
    total_kept = len(dedup)
    animal_rows = sum(1 for r in dedup.values() if r["has_animal"] == 1)
    human_rows = sum(1 for r in dedup.values() if r["has_human"] == 1 and r["has_animal"] == 0)
    species_filled = sum(1 for r in dedup.values() if r["species"] and r["species"] not in ("", "unknown", "blank"))

    species_counts = {}
    for r in dedup.values():
        s = r["species"]
        if s:
            species_counts[s] = species_counts.get(s, 0) + 1

    print(f"wrote {total_kept} rows -> {out_csv}")
    print(f"\nunmatched: {len(unmatched)} -> {UNMATCHED_CSV}")
    print(f"summary: {SUMMARY_JSON}")
    print(f"\nSummary:")
    print(f"  Total images processed: {total_input}")
    print(f"  With animal or human: {animal_rows + human_rows}")
    print(f"    Animals: {animal_rows}")
    print(f"    Humans only: {human_rows}")
    print(f"  Blank/vehicle (will be excluded from final output): {blank_or_vehicle}")
    print(f"  Species identified: {species_filled}/{animal_rows + human_rows}")
    print(f"\n  Species breakdown:")
    for species, count in sorted(species_counts.items(), key=lambda x: -x[1]):
        print(f"    {species}: {count}")


def run_megadetector(manifest_csv: Path, md_json: Path, out_csv: Path, threshold: float) -> None:
    """
    Convert MegaDetector results into the same per-image CSV schema.
    Species is left blank/unknown because MegaDetector does not classify species.
    """
    if not md_json.exists():
        raise FileNotFoundError(f"MegaDetector results not found: {md_json}")

    manifest_by_local = _read_manifest_index_by_local_name(manifest_csv)

    with open(md_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    images = data.get("images", data.get("predictions", [])) or []

    rows = []
    for img in images:
        # MegaDetector typically uses "file"
        file_field = (img.get("file") or img.get("file_name") or img.get("filepath") or "").strip()
        local_name = Path(file_field).name if file_field else ""
        if not local_name:
            continue

        manifest_row = manifest_by_local.get(local_name)
        if not manifest_row:
            continue

        detections = img.get("detections") or []
        animal_conf = _max_detection_conf(detections, ANIMAL_CATEGORY, threshold)
        human_conf = _max_detection_conf(detections, PERSON_CATEGORY, threshold)

        has_animal = 1 if animal_conf > 0 else 0
        has_human = 1 if human_conf > 0 else 0

        if has_animal == 0 and has_human == 0:
            continue

        model_certainty = max(animal_conf, human_conf)

        rows.append({
            "file_id": manifest_row.get("file_id", ""),
            "local_file_name": manifest_row.get("local_file_name", ""),
            "local_path": manifest_row.get("local_path", ""),
            "has_animal": has_animal,
            "has_human": has_human,
            "species": "animal" if has_animal else "human",
            "model_certainty": model_certainty,
        })

    # Deduplicate by file_id (keep the best certainty)
    dedup = {}
    for row in rows:
        fid = row.get("file_id", "")
        if not fid:
            continue
        if fid not in dedup:
            dedup[fid] = row
        else:
            if _safe_float(row.get("model_certainty", 0.0)) > _safe_float(dedup[fid].get("model_certainty", 0.0)):
                dedup[fid] = row

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["file_id", "local_file_name", "local_path", "has_animal", "has_human", "species", "model_certainty"]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(dedup.values())

    print(f"wrote {len(dedup)} rows -> {out_csv}")


def main():
    parser = argparse.ArgumentParser(description="Convert ML results into a per-image CSV keyed by file_id.")
    parser.add_argument("--provider", default="speciesnet", choices=["speciesnet", "megadetector"],
                        help="Which ML results format to parse.")
    parser.add_argument("--manifest", default=str(MANIFEST), help="Path to manifest.csv.")
    parser.add_argument("--speciesnet_json", default=str(SPECIESNET_JSON), help="Path to speciesnet_results.json.")
    parser.add_argument("--megadetector_json", default=str(MEGADETECTOR_JSON), help="Path to md_results.json.")
    parser.add_argument("--out", default=str(OUT_ML), help="Output ml_outputs.csv path.")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="Detection confidence threshold.")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    out_path = Path(args.out)

    if args.provider == "speciesnet":
        run_speciesnet(manifest_path, Path(args.speciesnet_json), out_path, args.threshold)
    else:
        run_megadetector(manifest_path, Path(args.megadetector_json), out_path, args.threshold)


if __name__ == "__main__":
    main()
    