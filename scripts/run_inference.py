# Converts model outputs into a simple per-image CSV keyed by file_id.
# Supports MegaDetector-style JSON (common format).
# NEW: Enhanced error logging, validation, and support for is_blank column

import csv
import json
import logging
from pathlib import Path
from datetime import datetime

# Setup logging
LOG_FILE = Path("data/outputs/inference_log.txt")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

MANIFEST = Path("data/outputs/manifest.csv")
MD_RESULTS_JSON = Path("data/outputs/md_results.json")
OUT_ML = Path("data/outputs/ml_outputs.csv")
ERROR_LOG = Path("data/outputs/inference_errors.csv")

# MegaDetector category mapping:
# 1 = animal, 2 = person, 3 = vehicle
ANIMAL_CATEGORY = {"1", 1, "animal"}
PERSON_CATEGORY = {"2", 2, "person"}
VEHICLE_CATEGORY = {"3", 3, "vehicle"}

DEFAULT_THRESHOLD = 0.5

# Required output columns
FIELDNAMES = ["file_id", "has_animal", "is_blank", "species", "count", "model_certainty"]


def load_manifest_index():
    """Build indices to match MegaDetector 'file' entries back to our file_id."""
    by_local_path = {}
    by_basename = {}
    all_file_ids = set()

    if not MANIFEST.exists():
        logger.warning(f"Manifest not found: {MANIFEST}")
        return by_local_path, by_basename, all_file_ids

    with open(MANIFEST, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fid = row.get("file_id", "")
            lp = row.get("local_path", "")
            bn = Path(lp).name if lp else row.get("local_file_name", "")
            if fid:
                all_file_ids.add(fid)
                if lp:
                    by_local_path[lp] = fid
                if bn:
                    by_basename[bn] = fid
    
    logger.info(f"Loaded manifest with {len(all_file_ids)} files")
    return by_local_path, by_basename, all_file_ids


def find_file_id(md_file: str, by_local_path: dict, by_basename: dict):
    """Match MegaDetector file path to our file_id."""
    if not md_file:
        return ""
    if md_file in by_local_path:
        return by_local_path[md_file]
    bn = Path(md_file).name
    return by_basename.get(bn, "")


def parse_detections(detections: list, threshold: float = DEFAULT_THRESHOLD):
    """
    Parse MegaDetector detections and return classification info.
    
    Returns:
        dict with has_animal, is_blank, count, model_certainty
    """
    animal_confs = []
    animal_count = 0
    max_conf = 0.0
    
    for det in detections:
        cat = det.get("category")
        conf = det.get("conf")
        
        if conf is None:
            continue
            
        try:
            conf_f = float(conf)
        except (ValueError, TypeError):
            continue
        
        max_conf = max(max_conf, conf_f)
        
        if cat in ANIMAL_CATEGORY:
            animal_confs.append(conf_f)
            if conf_f >= threshold:
                animal_count += 1
    
    max_animal_conf = max(animal_confs) if animal_confs else 0.0
    has_animal = 1 if max_animal_conf >= threshold else 0
    is_blank = 0 if has_animal else 1
    
    return {
        "has_animal": has_animal,
        "is_blank": is_blank,
        "count": animal_count if has_animal else 0,
        "model_certainty": round(max_animal_conf, 4) if animal_confs else round(max_conf, 4),
    }


def log_error(error_rows: list, file_id: str, file_path: str, error_type: str, message: str):
    """Log an error for later review."""
    error_rows.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "file_id": file_id,
        "file_path": file_path,
        "error_type": error_type,
        "message": message,
    })
    logger.warning(f"{error_type}: {message} (file_id={file_id})")


def write_error_log(error_rows: list):
    """Write error log to CSV."""
    if not error_rows:
        return
    
    ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ERROR_LOG, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp", "file_id", "file_path", "error_type", "message"])
        w.writeheader()
        w.writerows(error_rows)
    logger.info(f"Wrote {len(error_rows)} errors to {ERROR_LOG}")


def create_empty_output(all_file_ids: set):
    """Create ml_outputs.csv with empty values for all files in manifest."""
    rows = []
    for fid in all_file_ids:
        rows.append({
            "file_id": fid,
            "has_animal": "",
            "is_blank": "",
            "species": "",
            "count": "",
            "model_certainty": "",
        })
    
    with open(OUT_ML, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)
    
    logger.info(f"Created empty ml_outputs.csv with {len(rows)} rows (no model results available)")


def main():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_ML.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info("=" * 50)
    logger.info("Starting inference processing")
    
    by_local_path, by_basename, all_file_ids = load_manifest_index()
    error_rows = []
    
    # If no MegaDetector results, create empty output
    if not MD_RESULTS_JSON.exists():
        logger.warning(f"MegaDetector results not found: {MD_RESULTS_JSON}")
        create_empty_output(all_file_ids)
        print(f"md_results.json not found -> wrote empty {OUT_ML}")
        print("To generate ML results, run MegaDetector on images in data/staging/")
        return
    
    # Load MegaDetector results
    try:
        with open(MD_RESULTS_JSON, "r", encoding="utf-8") as f:
            md = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {MD_RESULTS_JSON}: {e}")
        create_empty_output(all_file_ids)
        return
    
    images = md.get("images", [])
    logger.info(f"Processing {len(images)} images from MegaDetector results")
    
    rows = []
    matched_ids = set()
    
    for img in images:
        md_file = img.get("file") or img.get("filename") or ""
        fid = find_file_id(md_file, by_local_path, by_basename)
        
        if not fid:
            log_error(error_rows, "", md_file, "UNMATCHED_FILE", 
                     f"Could not match MegaDetector file to manifest: {md_file}")
            continue
        
        matched_ids.add(fid)
        dets = img.get("detections") or []
        
        # Check for failure
        if img.get("failure"):
            log_error(error_rows, fid, md_file, "DETECTION_FAILED",
                     f"MegaDetector failed on this image: {img.get('failure')}")
            rows.append({
                "file_id": fid,
                "has_animal": "",
                "is_blank": "",
                "species": "",
                "count": "",
                "model_certainty": "",
            })
            continue
        
        # Parse detections
        result = parse_detections(dets)
        
        rows.append({
            "file_id": fid,
            "has_animal": result["has_animal"],
            "is_blank": result["is_blank"],
            "species": "",  # Future: species classification
            "count": result["count"],
            "model_certainty": result["model_certainty"],
        })
    
    # Add entries for files not in MegaDetector results
    missing_ids = all_file_ids - matched_ids
    if missing_ids:
        logger.warning(f"{len(missing_ids)} files in manifest but not in MegaDetector results")
        for fid in missing_ids:
            log_error(error_rows, fid, "", "MISSING_FROM_MODEL",
                     "File in manifest but not processed by MegaDetector")
            rows.append({
                "file_id": fid,
                "has_animal": "",
                "is_blank": "",
                "species": "",
                "count": "",
                "model_certainty": "",
            })
    
    # Deduplicate by file_id (keep last)
    dedup = {r["file_id"]: r for r in rows}
    
    # Write output
    with open(OUT_ML, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(dedup.values())
    
    # Write error log
    write_error_log(error_rows)
    
    # Summary
    total = len(dedup)
    with_results = sum(1 for r in dedup.values() if r["has_animal"] != "")
    animals = sum(1 for r in dedup.values() if r["has_animal"] == 1)
    blanks = sum(1 for r in dedup.values() if r["is_blank"] == 1)
    
    logger.info(f"Wrote {total} rows to {OUT_ML}")
    logger.info(f"  - With ML results: {with_results}")
    logger.info(f"  - Animals detected: {animals}")
    logger.info(f"  - Blank images: {blanks}")
    logger.info(f"  - Errors: {len(error_rows)}")
    
    print(f"\nInference complete:")
    print(f"  Total images: {total}")
    print(f"  With ML results: {with_results}")
    print(f"  Animals: {animals}, Blanks: {blanks}")
    print(f"  Errors logged: {len(error_rows)}")
    print(f"Output: {OUT_ML}")


if __name__ == "__main__":
    main()
