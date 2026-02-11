# Converts model outputs into a simple per-image CSV keyed by file_id.
# Supports:
#   - MegaDetector JSON (animal/person/vehicle detection)
#   - SpeciesNet JSON (species classification)
#
# Species labels are simplified to match Julie's spreadsheet format:
#   coyote, rabbit, raccoon, squirrel, bird, opossum, skunk, bobcat, human, etc.

import csv
import json
from pathlib import Path

MANIFEST = Path("data/outputs/manifest.csv")
MD_RESULTS_JSON = Path("data/outputs/md_results.json")
SPECIESNET_JSON = Path("data/outputs/speciesnet_results.json")
OUT_ML = Path("data/outputs/ml_outputs.csv")

# MegaDetector category mapping
ANIMAL_CATEGORY = {"1", 1}
PERSON_CATEGORY = {"2", 2}
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
    # parts[0] = uuid, [1] = class, [2] = order, [3] = family,
    # [4] = genus, [5] = species, [6] = common_name

    # Check fields from most specific to least specific
    # Order: common_name, "genus species", species, genus, family, order, class
    fields_to_check = []

    # Common name (index 6)
    if len(parts) > 6 and parts[6].strip():
        fields_to_check.append(parts[6].strip().lower())

    # "genus species" combined (index 4 + 5)
    if len(parts) > 5 and parts[4].strip() and parts[5].strip():
        fields_to_check.append(f"{parts[4].strip()} {parts[5].strip()}".lower())

    # Species (index 5)
    if len(parts) > 5 and parts[5].strip():
        fields_to_check.append(parts[5].strip().lower())

    # Genus (index 4)
    if len(parts) > 4 and parts[4].strip():
        fields_to_check.append(parts[4].strip().lower())

    # Family (index 3)
    if len(parts) > 3 and parts[3].strip():
        fields_to_check.append(parts[3].strip().lower())

    # Order (index 2)
    if len(parts) > 2 and parts[2].strip():
        fields_to_check.append(parts[2].strip().lower())

    # Class (index 1)
    if len(parts) > 1 and parts[1].strip():
        fields_to_check.append(parts[1].strip().lower())

    # Try each field against the map
    for field in fields_to_check:
        if field in SPECIES_MAP:
            return SPECIES_MAP[field]

    # If nothing matched, return the common name as-is (or empty)
    if len(parts) > 6 and parts[6].strip():
        return parts[6].strip().lower()

    return "unknown"


def load_manifest_index():
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


def load_speciesnet_results() -> dict:
    """
    Load SpeciesNet predictions keyed by basename.
    Returns dict: { basename: { "label": "squirrel", "confidence": 0.89 } }
    """
    if not SPECIESNET_JSON.exists():
        return {}

    with open(SPECIESNET_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    species_by_file = {}
    predictions = data.get("predictions", [])

    for pred in predictions:
        filepath = pred.get("filepath", "")
        prediction_str = pred.get("prediction", "")
        prediction_score = pred.get("prediction_score", 0.0)

        if not filepath:
            continue

        label = parse_species_label(prediction_str)

        # Skip blank/empty predictions
        if not label or label in ("blank", "empty"):
            continue

        basename = Path(filepath).name
        species_by_file[basename] = {
            "label": label,
            "confidence": prediction_score,
        }

    return species_by_file


def main():
    OUT_ML.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["file_id", "has_animal", "has_human", "species", "count", "model_certainty"]

    by_local_path, by_basename = load_manifest_index()

    species_data = load_speciesnet_results()
    if species_data:
        print(f"Loaded SpeciesNet results for {len(species_data)} images")
    else:
        print("No SpeciesNet results found (species column will be blank)")

    if not MD_RESULTS_JSON.exists():
        with open(OUT_ML, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
        print(f"md_results.json not found -> wrote empty {OUT_ML}")
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
        person_confs = []
        animal_count = 0
        person_count = 0

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
            elif cat in PERSON_CATEGORY:
                person_confs.append(conf_f)
                if conf_f >= DEFAULT_THRESHOLD:
                    person_count += 1

        max_animal_conf = max(animal_confs) if animal_confs else 0.0
        max_person_conf = max(person_confs) if person_confs else 0.0
        has_animal = 1 if max_animal_conf >= DEFAULT_THRESHOLD else 0
        has_human = 1 if max_person_conf >= DEFAULT_THRESHOLD else 0

        # Skip blank/vehicle-only images
        if not has_animal and not has_human:
            continue

        # Determine species
        if has_human and not has_animal:
            species = "human"
            best_conf = max_person_conf
            count = person_count
        elif has_animal:
            basename = Path(md_file).name
            sn = species_data.get(basename, {})
            species = sn.get("label", "unknown")
            best_conf = max_animal_conf
            count = animal_count
        else:
            species = ""
            best_conf = 0.0
            count = 0

        rows.append({
            "file_id": fid,
            "has_animal": has_animal,
            "has_human": has_human,
            "species": species,
            "count": count,
            "model_certainty": round(best_conf, 4),
        })

    # Deduplicate by file_id
    dedup = {r["file_id"]: r for r in rows}

    with open(OUT_ML, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(dedup.values())

    # Summary
    animal_rows = sum(1 for r in dedup.values() if r["has_animal"] == 1)
    human_rows = sum(1 for r in dedup.values() if r["has_human"] == 1 and r["has_animal"] == 0)
    species_filled = sum(1 for r in dedup.values() if r["species"] and r["species"] != "unknown")
    total_input = len(images)
    total_kept = len(dedup)
    total_skipped = total_input - total_kept

    # Count species distribution
    species_counts = {}
    for r in dedup.values():
        s = r["species"]
        if s:
            species_counts[s] = species_counts.get(s, 0) + 1

    print(f"wrote {total_kept} rows -> {OUT_ML}")
    print(f"\nSummary:")
    print(f"  Total images processed: {total_input}")
    print(f"  Kept (animal or human): {total_kept}")
    print(f"    Animals: {animal_rows}")
    print(f"    Humans only: {human_rows}")
    print(f"  Skipped (blank/vehicle): {total_skipped}")
    print(f"  Species identified: {species_filled}/{total_kept}")
    print(f"\n  Species breakdown:")
    for species, count in sorted(species_counts.items(), key=lambda x: -x[1]):
        print(f"    {species}: {count}")


if __name__ == "__main__":
    main()