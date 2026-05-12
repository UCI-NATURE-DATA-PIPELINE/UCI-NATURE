# Converts SpeciesNet output into a simple per-image CSV keyed by file_id.
#
# SpeciesNet runs detector + classifier internally, so speciesnet_results.json
# includes both detection boxes and a ranked classifier candidate list. The
# pipeline keeps the best species/taxon label the model actually produced and
# only falls back to animal_unclassified when the model provides no usable
# taxonomic label at all.

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ml.speciesnet_parsing import (
    ANIMAL_UNCLASSIFIED,
    dump_candidate_labels_json,
    resolve_prediction,
    safe_float,
)

MANIFEST = Path("data/outputs/manifest.csv")
SPECIESNET_JSON = Path("data/outputs/speciesnet_results.json")
MEGADETECTOR_JSON = Path("data/outputs/md_results.json")
OUT_ML = Path("data/outputs/ml_outputs.csv")

LOG_DIR = Path("data/outputs/logs")
UNMATCHED_CSV = LOG_DIR / "unmatched_predictions.csv"
SUMMARY_JSON = LOG_DIR / "ml_summary.json"

ANIMAL_CATEGORY = {"1", "animal"}
PERSON_CATEGORY = {"2", "human"}
DEFAULT_THRESHOLD = 0.5
DEFAULT_PRESENCE_THRESHOLD = 0.15
DEFAULT_COUNT_THRESHOLD = 0.5


def _normalize_path(path_value: str) -> str:
    path_value = (path_value or "").strip().replace("\\", "/")
    while "//" in path_value:
        path_value = path_value.replace("//", "/")
    if path_value.startswith("./"):
        path_value = path_value[2:]
    return path_value


def _tail_key(filepath: str, n_parts: int) -> str:
    parts = PurePosixPath(_normalize_path(filepath)).parts
    if len(parts) <= n_parts:
        return str(PurePosixPath(*parts))
    return str(PurePosixPath(*parts[-n_parts:]))


def _folder_key(filepath: str) -> str:
    parts = _normalize_path(filepath).split("/")
    return parts[-2] if len(parts) >= 2 else ""


def _read_manifest_indexes(manifest_path: Path) -> dict[str, dict]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    by_local_name: dict[str, list[dict]] = defaultdict(list)
    by_basename: dict[str, list[dict]] = defaultdict(list)
    by_local_path: dict[str, dict] = {}
    by_tail: dict[str, list[dict]] = defaultdict(list)

    with open(manifest_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            local_name = (row.get("local_file_name") or "").strip()
            local_path = _normalize_path(row.get("local_path") or "")
            if local_name:
                by_local_name[local_name].append(row)
                by_basename[Path(local_name).name].append(row)
            if local_path:
                by_local_path[local_path] = row
                by_basename[PurePosixPath(local_path).name].append(row)
                for n_parts in (2, 3, 4, 5):
                    by_tail[_tail_key(local_path, n_parts)].append(row)

    return {
        "by_local_name": by_local_name,
        "by_basename": by_basename,
        "by_local_path": by_local_path,
        "by_tail": by_tail,
    }


def _resolve_manifest_row(indexes: dict[str, dict], prediction: dict) -> dict | None:
    filepath = _normalize_path(prediction.get("filepath") or "")
    local_name = (prediction.get("file") or prediction.get("file_name") or "").strip()
    if not local_name and filepath:
        local_name = PurePosixPath(filepath).name
    local_name = Path(local_name).name

    candidates = indexes["by_local_name"].get(local_name, []) if local_name else []
    if len(candidates) == 1:
        return candidates[0]

    if filepath and filepath in indexes["by_local_path"]:
        return indexes["by_local_path"][filepath]

    if filepath:
        for n_parts in (2, 3, 4, 5):
            candidates = indexes["by_tail"].get(_tail_key(filepath, n_parts), [])
            if len(candidates) == 1:
                return candidates[0]
            if len(candidates) > 1:
                folder = _folder_key(filepath)
                folder_matches = [
                    candidate
                    for candidate in candidates
                    if _folder_key(candidate.get("local_path") or "") == folder
                ]
                if len(folder_matches) == 1:
                    return folder_matches[0]

    basename = PurePosixPath(filepath).name if filepath else local_name
    candidates = indexes["by_basename"].get(basename, []) if basename else []
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1 and filepath:
        folder = _folder_key(filepath)
        folder_matches = [
            candidate
            for candidate in candidates
            if _folder_key(candidate.get("local_path") or "") == folder
        ]
        if len(folder_matches) == 1:
            return folder_matches[0]

    return None


def _count_detections(detections: list[dict], categories: set[str], threshold: float) -> int:
    count = 0
    for detection in detections or []:
        category = str(detection.get("category", "")).lower()
        confidence = safe_float(
            detection.get("conf", detection.get("confidence", 0.0)),
            0.0,
        )
        if category in categories and confidence >= threshold:
            count += 1
    return count


def _max_detection_conf(detections: list[dict], categories: set[str], threshold: float) -> float:
    best = 0.0
    for detection in detections or []:
        category = str(detection.get("category", "")).lower()
        confidence = safe_float(
            detection.get("conf", detection.get("confidence", 0.0)),
            0.0,
        )
        if category in categories and confidence >= threshold and confidence > best:
            best = confidence
    return best


def _max_detection_conf_any(detections: list[dict], categories: set[str]) -> float:
    best = 0.0
    for detection in detections or []:
        category = str(detection.get("category", "")).lower()
        confidence = safe_float(
            detection.get("conf", detection.get("confidence", 0.0)),
            0.0,
        )
        if category in categories and confidence > best:
            best = confidence
    return best


def _deduplicate_rows_by_file_id(rows: list[dict]) -> dict[str, dict]:
    deduped: dict[str, dict] = {}
    for row in rows:
        file_id = row.get("file_id", "") or row.get("local_path", "") or row.get("local_file_name", "")
        if not file_id:
            continue
        if file_id not in deduped:
            deduped[file_id] = row
            continue

        current_has_animal = int(safe_float(deduped[file_id].get("has_animal", 0), 0.0))
        new_has_animal = int(safe_float(row.get("has_animal", 0), 0.0))
        if new_has_animal > current_has_animal:
            deduped[file_id] = row
            continue

        current_species_level = int(safe_float(deduped[file_id].get("species_level", 0), 0.0))
        new_species_level = int(safe_float(row.get("species_level", 0), 0.0))
        if new_species_level > current_species_level:
            deduped[file_id] = row
            continue

        current_confidence = safe_float(deduped[file_id].get("model_certainty", 0.0))
        new_confidence = safe_float(row.get("model_certainty", 0.0))
        if new_confidence > current_confidence:
            deduped[file_id] = row

    return deduped


def _write_output_csv(out_csv: Path, rows_by_file_id: dict[str, dict]) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "file_id",
        "local_file_name",
        "local_path",
        "has_animal",
        "has_human",
        "animal_count",
        "human_count",
        "count",
        "species",
        "species_level",
        "species_rank",
        "species_raw",
        "model_certainty",
        "prediction_label_raw",
        "prediction_score_raw",
        "prediction_source",
        "resolved_source",
        "classification_candidates_json",
        "species_records_json",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_by_file_id.values())


def _write_unmatched(unmatched: list[dict]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(UNMATCHED_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["provider", "pred_file"])
        writer.writeheader()
        writer.writerows(unmatched)


def _build_species_records(
    *,
    species: str,
    species_raw: str,
    model_certainty: float,
    prediction_source: str,
    species_rank: str,
    species_level: int,
    count: int,
) -> str:
    if not species:
        return ""

    records = [
        {
            "species": species,
            "species_raw": species_raw,
            "model_certainty": round(safe_float(model_certainty, 0.0), 6),
            "prediction_source": prediction_source,
            "species_rank": species_rank,
            "species_level": int(bool(species_level)),
            "count": max(1, int(count or 1)),
        }
    ]
    return json.dumps(records, ensure_ascii=False)


def run_speciesnet(
    manifest_csv: Path,
    speciesnet_json: Path,
    out_csv: Path,
    threshold: float,
    presence_threshold: float | None = None,
    count_threshold: float | None = None,
) -> dict:
    if not speciesnet_json.exists():
        raise FileNotFoundError(f"SpeciesNet results not found: {speciesnet_json}")

    presence_threshold = threshold if presence_threshold is None else presence_threshold
    count_threshold = threshold if count_threshold is None else count_threshold

    manifest_indexes = _read_manifest_indexes(manifest_csv)

    with open(speciesnet_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    predictions = data.get("predictions", []) or []

    rows: list[dict] = []
    unmatched: list[dict] = []

    for prediction in predictions:
        manifest_row = _resolve_manifest_row(manifest_indexes, prediction)
        if not manifest_row:
            unmatched.append(
                {
                    "provider": "speciesnet",
                    "pred_file": (
                        prediction.get("file")
                        or prediction.get("file_name")
                        or Path(prediction.get("filepath", "")).name
                        or ""
                    ).strip(),
                }
            )
            continue

        detections = prediction.get("detections") or []

        animal_presence_count = _count_detections(
            detections,
            ANIMAL_CATEGORY,
            presence_threshold,
        )
        human_presence_count = _count_detections(
            detections,
            PERSON_CATEGORY,
            presence_threshold,
        )
        animal_count = _count_detections(detections, ANIMAL_CATEGORY, count_threshold)
        human_count = _count_detections(detections, PERSON_CATEGORY, count_threshold)

        has_animal = 1 if animal_presence_count > 0 else 0
        has_human = 1 if human_presence_count > 0 else 0

        resolved = resolve_prediction(
            prediction,
            has_animal=bool(has_animal),
            has_human=bool(has_human),
        )

        if has_animal == 0 and has_human == 0:
            rows.append(
                {
                    "file_id": manifest_row.get("file_id", ""),
                    "local_file_name": manifest_row.get("local_file_name", ""),
                    "local_path": manifest_row.get("local_path", ""),
                    "has_animal": 0,
                    "has_human": 0,
                    "animal_count": 0,
                    "human_count": 0,
                    "count": "",
                    "species": "blank",
                    "species_level": 0,
                    "species_rank": resolved.get("resolved_rank", ""),
                    "species_raw": resolved.get("resolved_label_raw", ""),
                    "model_certainty": "",
                    "prediction_label_raw": resolved.get("raw_prediction_label", ""),
                    "prediction_score_raw": round(
                        safe_float(resolved.get("raw_prediction_score", 0.0), 0.0),
                        6,
                    ),
                    "prediction_source": resolved.get("prediction_source", ""),
                    "resolved_source": resolved.get("resolved_source", ""),
                    "classification_candidates_json": resolved.get(
                        "classification_candidates_json",
                        "[]",
                    ),
                    "species_records_json": "",
                }
            )
            continue

        species = resolved.get("resolved_label", "")
        species_level = int(bool(resolved.get("resolved_species_level")))
        model_certainty = safe_float(resolved.get("resolved_score", 0.0), 0.0)

        presence_row_count = animal_presence_count if has_animal else human_presence_count
        count_row_count = animal_count if has_animal else human_count
        row_count = count_row_count if count_row_count > 0 else presence_row_count

        if has_human == 1 and has_animal == 0:
            species = "human"
            species_level = 0
            model_certainty = max(
                model_certainty,
                _max_detection_conf(detections, PERSON_CATEGORY, presence_threshold),
                _max_detection_conf_any(detections, PERSON_CATEGORY),
            )

        if has_animal == 1 and not species:
            species = ANIMAL_UNCLASSIFIED
            species_level = 0

        if has_animal == 1:
            model_certainty = max(
                model_certainty,
                _max_detection_conf(detections, ANIMAL_CATEGORY, presence_threshold),
                _max_detection_conf_any(detections, ANIMAL_CATEGORY),
            )

        rows.append(
            {
                "file_id": manifest_row.get("file_id", ""),
                "local_file_name": manifest_row.get("local_file_name", ""),
                "local_path": manifest_row.get("local_path", ""),
                "has_animal": has_animal,
                "has_human": has_human,
                "animal_count": animal_count,
                "human_count": human_count,
                "count": row_count if row_count > 0 else "",
                "species": species,
                "species_level": species_level,
                "species_rank": resolved.get("resolved_rank", ""),
                "species_raw": resolved.get("resolved_label_raw", ""),
                "model_certainty": round(model_certainty, 6) if model_certainty else "",
                "prediction_label_raw": resolved.get("raw_prediction_label", ""),
                "prediction_score_raw": round(
                    safe_float(resolved.get("raw_prediction_score", 0.0), 0.0),
                    6,
                ),
                "prediction_source": resolved.get("prediction_source", ""),
                "resolved_source": resolved.get("resolved_source", ""),
                "classification_candidates_json": resolved.get(
                    "classification_candidates_json",
                    dump_candidate_labels_json([]),
                ),
                "species_records_json": _build_species_records(
                    species=species,
                    species_raw=resolved.get("resolved_label_raw", "") or species,
                    model_certainty=model_certainty,
                    prediction_source=resolved.get("resolved_source", ""),
                    species_rank=resolved.get("resolved_rank", ""),
                    species_level=species_level,
                    count=row_count,
                )
                if has_animal
                else "",
            }
        )

    deduped = _deduplicate_rows_by_file_id(rows)

    _write_output_csv(out_csv, deduped)
    _write_unmatched(unmatched)

    total_input = len(predictions)
    total_rows_written = len(deduped)
    animal_rows = sum(1 for row in deduped.values() if row["has_animal"] == 1)
    resolved_species_rows = sum(
        1
        for row in deduped.values()
        if row["has_animal"] == 1 and str(row.get("species_level", "0")) == "1"
    )
    animal_unclassified_rows = max(animal_rows - resolved_species_rows, 0)
    human_rows = sum(
        1
        for row in deduped.values()
        if row["has_human"] == 1 and row["has_animal"] == 0
    )
    blank_rows = sum(
        1
        for row in deduped.values()
        if row["has_animal"] == 0 and row["has_human"] == 0
    )

    summary = {
        "provider": "speciesnet",
        "total_predictions_in_json": total_input,
        "matched_to_manifest": total_input - len(unmatched),
        "unmatched_to_manifest": len(unmatched),
        "rows_written_to_ml_outputs": total_rows_written,
        "animal_rows": animal_rows,
        "animal_unclassified_rows": animal_unclassified_rows,
        "resolved_species_rows": resolved_species_rows,
        "human_only_rows": human_rows,
        "blank_or_vehicle_rows": blank_rows,
        "threshold": threshold,
        "presence_threshold": presence_threshold,
        "count_threshold": count_threshold,
        "out_csv": str(out_csv),
        "unmatched_csv": str(UNMATCHED_CSV),
    }
    summary["unmatched_rate"] = round(
        (len(unmatched) / total_input) if total_input else 0.0,
        6,
    )

    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    species_counts: dict[str, int] = {}
    for row in deduped.values():
        species = (row.get("species") or "").strip()
        if species:
            species_counts[species] = species_counts.get(species, 0) + 1

    print(f"wrote {total_rows_written} rows -> {out_csv}")
    print(f"\nunmatched: {len(unmatched)} -> {UNMATCHED_CSV}")
    print(f"summary: {SUMMARY_JSON}")
    print("\nSummary:")
    print(f"  Total images processed: {total_input}")
    print(f"  Rows written to ml_outputs.csv: {total_rows_written}")
    print(f"    Animals: {animal_rows}")
    print(f"    Resolved species: {resolved_species_rows}")
    print(f"    Animal unclassified: {animal_unclassified_rows}")
    print(f"    Humans only: {human_rows}")
    print(f"    Blank/vehicle: {blank_rows}")
    print(f"\n  Thresholds:")
    print(f"    Presence threshold: {presence_threshold}")
    print(f"    Count threshold: {count_threshold}")
    print("\n  Species / taxon breakdown:")
    for species, count in sorted(species_counts.items(), key=lambda item: (-item[1], item[0])):
        print(f"    {species}: {count}")

    return summary


def run_megadetector(
    manifest_csv: Path,
    md_json: Path,
    out_csv: Path,
    threshold: float,
    presence_threshold: float | None = None,
    count_threshold: float | None = None,
) -> dict:
    if not md_json.exists():
        raise FileNotFoundError(f"MegaDetector results not found: {md_json}")

    presence_threshold = threshold if presence_threshold is None else presence_threshold
    count_threshold = threshold if count_threshold is None else count_threshold

    manifest_indexes = _read_manifest_indexes(manifest_csv)

    with open(md_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    images = data.get("images", data.get("predictions", [])) or []

    rows: list[dict] = []
    unmatched: list[dict] = []

    for image in images:
        manifest_row = _resolve_manifest_row(manifest_indexes, image)
        if not manifest_row:
            file_field = (
                image.get("file")
                or image.get("file_name")
                or image.get("filepath")
                or ""
            ).strip()
            unmatched.append(
                {
                    "provider": "megadetector",
                    "pred_file": Path(file_field).name if file_field else "",
                }
            )
            continue

        detections = image.get("detections") or []
        animal_presence_count = _count_detections(detections, ANIMAL_CATEGORY, presence_threshold)
        human_presence_count = _count_detections(detections, PERSON_CATEGORY, presence_threshold)
        animal_count = _count_detections(detections, ANIMAL_CATEGORY, count_threshold)
        human_count = _count_detections(detections, PERSON_CATEGORY, count_threshold)
        animal_conf = max(
            _max_detection_conf(detections, ANIMAL_CATEGORY, presence_threshold),
            _max_detection_conf_any(detections, ANIMAL_CATEGORY),
        )
        human_conf = max(
            _max_detection_conf(detections, PERSON_CATEGORY, presence_threshold),
            _max_detection_conf_any(detections, PERSON_CATEGORY),
        )

        has_animal = 1 if animal_presence_count > 0 else 0
        has_human = 1 if human_presence_count > 0 else 0

        if has_animal == 0 and has_human == 0:
            rows.append(
                {
                    "file_id": manifest_row.get("file_id", ""),
                    "local_file_name": manifest_row.get("local_file_name", ""),
                    "local_path": manifest_row.get("local_path", ""),
                    "has_animal": 0,
                    "has_human": 0,
                    "animal_count": 0,
                    "human_count": 0,
                    "count": "",
                    "species": "blank",
                    "species_level": 0,
                    "species_rank": "",
                    "species_raw": "",
                    "model_certainty": "",
                    "prediction_label_raw": "",
                    "prediction_score_raw": "",
                    "prediction_source": "megadetector",
                    "resolved_source": "megadetector",
                    "classification_candidates_json": "[]",
                    "species_records_json": "",
                }
            )
            continue

        species = "human" if has_human and not has_animal else ANIMAL_UNCLASSIFIED
        model_certainty = max(animal_conf, human_conf)
        presence_row_count = animal_presence_count if has_animal else human_presence_count
        count_row_count = animal_count if has_animal else human_count
        row_count = count_row_count if count_row_count > 0 else presence_row_count

        rows.append(
            {
                "file_id": manifest_row.get("file_id", ""),
                "local_file_name": manifest_row.get("local_file_name", ""),
                "local_path": manifest_row.get("local_path", ""),
                "has_animal": has_animal,
                "has_human": has_human,
                "animal_count": animal_count,
                "human_count": human_count,
                "count": row_count if row_count > 0 else "",
                "species": species,
                "species_level": 0,
                "species_rank": "",
                "species_raw": species,
                "model_certainty": round(model_certainty, 6) if model_certainty else "",
                "prediction_label_raw": "",
                "prediction_score_raw": "",
                "prediction_source": "megadetector",
                "resolved_source": "megadetector",
                "classification_candidates_json": "[]",
                "species_records_json": _build_species_records(
                    species=species,
                    species_raw=species,
                    model_certainty=model_certainty,
                    prediction_source="megadetector",
                    species_rank="",
                    species_level=0,
                    count=row_count,
                )
                if has_animal
                else "",
            }
        )

    deduped = _deduplicate_rows_by_file_id(rows)

    _write_output_csv(out_csv, deduped)
    _write_unmatched(unmatched)

    total_input = len(images)
    total_rows_written = len(deduped)
    animal_rows = sum(1 for row in deduped.values() if row["has_animal"] == 1)
    human_rows = sum(
        1
        for row in deduped.values()
        if row["has_human"] == 1 and row["has_animal"] == 0
    )
    blank_rows = sum(
        1
        for row in deduped.values()
        if row["has_animal"] == 0 and row["has_human"] == 0
    )

    summary = {
        "provider": "megadetector",
        "total_predictions_in_json": total_input,
        "matched_to_manifest": total_input - len(unmatched),
        "unmatched_to_manifest": len(unmatched),
        "rows_written_to_ml_outputs": total_rows_written,
        "animal_rows": animal_rows,
        "animal_unclassified_rows": animal_rows,
        "resolved_species_rows": 0,
        "human_only_rows": human_rows,
        "blank_or_vehicle_rows": blank_rows,
        "threshold": threshold,
        "presence_threshold": presence_threshold,
        "count_threshold": count_threshold,
        "out_csv": str(out_csv),
        "unmatched_csv": str(UNMATCHED_CSV),
    }
    summary["unmatched_rate"] = round(
        (len(unmatched) / total_input) if total_input else 0.0,
        6,
    )

    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"wrote {total_rows_written} rows -> {out_csv}")
    print(f"\nunmatched: {len(unmatched)} -> {UNMATCHED_CSV}")
    print(f"summary: {SUMMARY_JSON}")

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Convert ML results into a per-image CSV keyed by file_id."
    )
    parser.add_argument(
        "--provider",
        default="speciesnet",
        choices=["speciesnet", "megadetector"],
        help="Which ML results format to parse.",
    )
    parser.add_argument(
        "--manifest",
        default=str(MANIFEST),
        help="Path to manifest.csv.",
    )
    parser.add_argument(
        "--speciesnet_json",
        default=str(SPECIESNET_JSON),
        help="Path to speciesnet_results.json.",
    )
    parser.add_argument(
        "--megadetector_json",
        default=str(MEGADETECTOR_JSON),
        help="Path to md_results.json.",
    )
    parser.add_argument(
        "--out",
        default=str(OUT_ML),
        help="Output ml_outputs.csv path.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="Legacy/shared detection threshold. Used for both presence and count unless overridden.",
    )
    parser.add_argument(
        "--presence_threshold",
        type=float,
        default=DEFAULT_PRESENCE_THRESHOLD,
        help="Lower threshold used to decide whether an image contains an animal or human.",
    )
    parser.add_argument(
        "--count_threshold",
        type=float,
        default=DEFAULT_COUNT_THRESHOLD,
        help="Threshold used when counting detections for animal_count and human_count.",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    out_path = Path(args.out)

    if args.provider == "speciesnet":
        run_speciesnet(
            manifest_csv=manifest_path,
            speciesnet_json=Path(args.speciesnet_json),
            out_csv=out_path,
            threshold=args.threshold,
            presence_threshold=args.presence_threshold,
            count_threshold=args.count_threshold,
        )
    else:
        run_megadetector(
            manifest_csv=manifest_path,
            md_json=Path(args.megadetector_json),
            out_csv=out_path,
            threshold=args.threshold,
            presence_threshold=args.presence_threshold,
            count_threshold=args.count_threshold,
        )


if __name__ == "__main__":
    main()