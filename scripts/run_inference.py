# Converts model outputs into a simple per-image CSV keyed by file_id.
# Supports MegaDetector-style JSON (common format).
# NEW: Enhanced error logging, validation, and support for is_blank column

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Set, Tuple

from scripts.ml.base import MLProvider, MLRunResult, ProviderRegistry

# Setup logging
LOG_FILE = Path("data/outputs/inference_log.txt")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a"),
        logging.StreamHandler(),
    ],
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


def load_manifest_index(manifest_path: Path):
    """Build indices to match MegaDetector 'file' entries back to our file_id."""
    by_local_path = {}
    by_basename = {}
    all_file_ids = set()

    if not manifest_path.exists():
        logger.warning(f"Manifest not found: {manifest_path}")
        return by_local_path, by_basename, all_file_ids

    with open(manifest_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fid = (row.get("file_id") or "").strip()
            lp = (row.get("local_path") or "").strip()
            bn = Path(lp).name if lp else (row.get("local_file_name") or "").strip()
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
    error_rows.append(
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "file_id": file_id,
            "file_path": file_path,
            "error_type": error_type,
            "message": message,
        }
    )
    logger.warning(f"{error_type}: {message} (file_id={file_id})")


def write_error_log(error_rows: list, error_log_path: Path):
    """Write error log to CSV."""
    if not error_rows:
        return

    error_log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(error_log_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["timestamp", "file_id", "file_path", "error_type", "message"]
        )
        w.writeheader()
        w.writerows(error_rows)
    logger.info(f"Wrote {len(error_rows)} errors to {error_log_path}")


def create_empty_output(all_file_ids: set, output_csv: Path):
    """Create ml_outputs.csv with empty values for all files in manifest."""
    rows = []
    for fid in all_file_ids:
        rows.append(
            {
                "file_id": fid,
                "has_animal": "",
                "is_blank": "",
                "species": "",
                "count": "",
                "model_certainty": "",
            }
        )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)

    logger.info(f"Created empty ml_outputs.csv with {len(rows)} rows (no model results available)")


class MegaDetectorJsonProvider(MLProvider):
    name = "megadetector_json"

    def run(self, manifest_csv: Path, output_csv: Path, **opts: Any) -> MLRunResult:
        md_json_path: Path = Path(opts.get("md_json_path", MD_RESULTS_JSON))
        threshold: float = float(opts.get("threshold", DEFAULT_THRESHOLD))
        error_log_path: Path = Path(opts.get("error_log_path", ERROR_LOG))

        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        output_csv.parent.mkdir(parents=True, exist_ok=True)

        by_local_path, by_basename, all_file_ids = load_manifest_index(manifest_csv)
        error_rows: List[Dict[str, Any]] = []

        if not md_json_path.exists():
            logger.warning(f"MegaDetector results not found: {md_json_path}")
            create_empty_output(all_file_ids, output_csv)
            write_error_log(error_rows, error_log_path)
            print(f"md_results.json not found -> wrote empty {output_csv}")
            print("To generate ML results, run MegaDetector on images in data/staging/")
            return MLRunResult(
                output_csv=output_csv,
                provider_name=self.name,
                meta={"note": "md_json_missing", "threshold": threshold, "total": len(all_file_ids)},
            )

        try:
            with open(md_json_path, "r", encoding="utf-8") as f:
                md = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {md_json_path}: {e}")
            log_error(error_rows, "", str(md_json_path), "INVALID_JSON", str(e))
            create_empty_output(all_file_ids, output_csv)
            write_error_log(error_rows, error_log_path)
            return MLRunResult(
                output_csv=output_csv,
                provider_name=self.name,
                meta={"note": "invalid_json", "threshold": threshold, "total": len(all_file_ids)},
            )

        images = md.get("images", [])
        logger.info(f"Processing {len(images)} images from MegaDetector results")

        rows: List[Dict[str, Any]] = []
        matched_ids: Set[str] = set()

        for img in images:
            md_file = img.get("file") or img.get("filename") or ""
            fid = find_file_id(md_file, by_local_path, by_basename)

            if not fid:
                log_error(
                    error_rows,
                    "",
                    md_file,
                    "UNMATCHED_FILE",
                    f"Could not match MegaDetector file to manifest: {md_file}",
                )
                continue

            matched_ids.add(fid)
            dets = img.get("detections") or []

            if img.get("failure"):
                log_error(
                    error_rows,
                    fid,
                    md_file,
                    "DETECTION_FAILED",
                    f"MegaDetector failed on this image: {img.get('failure')}",
                )
                rows.append(
                    {
                        "file_id": fid,
                        "has_animal": "",
                        "is_blank": "",
                        "species": "",
                        "count": "",
                        "model_certainty": "",
                    }
                )
                continue

            result = parse_detections(dets, threshold=threshold)

            rows.append(
                {
                    "file_id": fid,
                    "has_animal": result["has_animal"],
                    "is_blank": result["is_blank"],
                    "species": "",
                    "count": result["count"],
                    "model_certainty": result["model_certainty"],
                }
            )

        missing_ids = all_file_ids - matched_ids
        if missing_ids:
            logger.warning(f"{len(missing_ids)} files in manifest but not in MegaDetector results")
            for fid in missing_ids:
                log_error(
                    error_rows,
                    fid,
                    "",
                    "MISSING_FROM_MODEL",
                    "File in manifest but not processed by MegaDetector",
                )
                rows.append(
                    {
                        "file_id": fid,
                        "has_animal": "",
                        "is_blank": "",
                        "species": "",
                        "count": "",
                        "model_certainty": "",
                    }
                )

        dedup = {r["file_id"]: r for r in rows}

        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDNAMES)
            w.writeheader()
            w.writerows(dedup.values())

        write_error_log(error_rows, error_log_path)

        total = len(dedup)
        with_results = sum(1 for r in dedup.values() if r["has_animal"] != "")
        animals = sum(1 for r in dedup.values() if r["has_animal"] == 1)
        blanks = sum(1 for r in dedup.values() if r["is_blank"] == 1)

        logger.info(f"Wrote {total} rows to {output_csv}")
        logger.info(f"  - With ML results: {with_results}")
        logger.info(f"  - Animals detected: {animals}")
        logger.info(f"  - Blank images: {blanks}")
        logger.info(f"  - Errors: {len(error_rows)}")

        print(f"\nInference complete:")
        print(f"  Total images: {total}")
        print(f"  With ML results: {with_results}")
        print(f"  Animals: {animals}, Blanks: {blanks}")
        print(f"  Errors logged: {len(error_rows)}")
        print(f"Output: {output_csv}")

        return MLRunResult(
            output_csv=output_csv,
            provider_name=self.name,
            meta={
                "threshold": threshold,
                "total": total,
                "with_results": with_results,
                "animals": animals,
                "blanks": blanks,
                "errors": len(error_rows),
                "md_json_path": str(md_json_path),
            },
        )


def build_registry() -> ProviderRegistry:
    reg = ProviderRegistry()
    reg.register(MegaDetectorJsonProvider())
    return reg


def main():
    parser = argparse.ArgumentParser(
        description="Converts ML outputs into ml_outputs.csv (provider-based)."
    )
    parser.add_argument("--provider", default="megadetector_json")
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--out", default=str(OUT_ML))

    parser.add_argument("--md-json", default=str(MD_RESULTS_JSON))
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--error-log", default=str(ERROR_LOG))

    args = parser.parse_args()

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 50)
    logger.info("Starting inference processing")

    reg = build_registry()
    provider = reg.get(args.provider)

    provider.run(
        manifest_csv=Path(args.manifest),
        output_csv=Path(args.out),
        md_json_path=Path(args.md_json),
        threshold=args.threshold,
        error_log_path=Path(args.error_log),
    )


if __name__ == "__main__":
    main()