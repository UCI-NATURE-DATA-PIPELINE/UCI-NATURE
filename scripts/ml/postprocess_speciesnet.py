# scripts/ml/postprocess_speciesnet.py

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ml.speciesnet_parsing import resolve_prediction, safe_float


IN_JSON = Path("data/outputs/speciesnet_results.json")
MANIFEST_CSV = Path("data/outputs/manifest.csv")
METADATA_CSV = Path("data/outputs/metadata.csv")

OUT_CSV = Path("data/outputs/speciesnet_results.csv")
REVIEW_CSV = Path("data/outputs/speciesnet_review.csv")

MOUNTED_JSON = Path("/mnt/data/speciesnet_results.json")

THRESH_NORMAL = 0.90
THRESH_GENERIC = 0.97
MARGIN_MIN = 0.20
BURST_WINDOW_SECONDS = 300
DETECTION_THRESHOLD = 0.5

ANIMAL_CATEGORY = {"1", "animal"}
PERSON_CATEGORY = {"2", "human"}


def normalize_path(path_value: str) -> str:
    path_value = (path_value or "").strip().replace("\\", "/")
    while "//" in path_value:
        path_value = path_value.replace("//", "/")
    if path_value.startswith("./"):
        path_value = path_value[2:]
    return path_value


def tail_key(filepath: str, n_parts: int) -> str:
    pure_path = PurePosixPath(normalize_path(filepath))
    parts = pure_path.parts
    if len(parts) <= n_parts:
        return str(pure_path)
    return str(PurePosixPath(*parts[-n_parts:]))


def folder_key_from_filepath(filepath: str) -> str:
    parts = normalize_path(filepath).split("/")
    if len(parts) >= 2:
        return parts[-2]
    return "unknown_folder"


def load_manifest_localpath_by_fileid(manifest_csv: Path = MANIFEST_CSV):
    manifest_csv = Path(manifest_csv)
    if not manifest_csv.exists():
        raise FileNotFoundError(f"Missing {manifest_csv}")

    with open(manifest_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = [name.strip() for name in (reader.fieldnames or [])]

        def pick_col(options):
            for column in fieldnames:
                if column.lower() in options:
                    return column
            return None

        fileid_col = pick_col({"file_id", "fileid", "id"})
        path_col = pick_col({"local_path", "filepath", "path"})

        if not fileid_col or not path_col:
            raise ValueError(
                f"{manifest_csv} must have file_id/id + local_path/filepath/path. Found: {fieldnames}"
            )

        output = {}
        for row in reader:
            file_id = (row.get(fileid_col) or "").strip()
            local_path = (row.get(path_col) or "").strip()
            if file_id and local_path:
                output[file_id] = normalize_path(local_path)

        return output


def parse_datetime_loose(value: str):
    if not value:
        return None

    value = str(value).strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S%z",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            pass

    if "." in value:
        base = value.split(".", 1)[0]
        for fmt in [
            "%Y-%m-%d %H:%M:%S",
            "%Y:%m:%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
        ]:
            try:
                return datetime.strptime(base, fmt)
            except Exception:
                pass

    return None


def load_exif_dt_by_fileid(metadata_csv: Path = METADATA_CSV):
    metadata_csv = Path(metadata_csv)
    if not metadata_csv.exists():
        raise FileNotFoundError(f"Missing {metadata_csv}")

    with open(metadata_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = [name.strip() for name in (reader.fieldnames or [])]

        def pick_col(options):
            for column in fieldnames:
                if column.lower() in options:
                    return column
            return None

        fileid_col = pick_col({"file_id", "fileid", "id"})
        if not fileid_col:
            raise ValueError(f"{metadata_csv} must have file_id/id. Found: {fieldnames}")

        exif_col = pick_col({"exif_datetime", "datetime", "exifdatetime", "date_time"})
        date_col = pick_col({"date"})
        time_col = pick_col({"time"})

        output = {}
        for row in reader:
            file_id = (row.get(fileid_col) or "").strip()
            if not file_id:
                continue

            dt = None
            if exif_col:
                dt = parse_datetime_loose(row.get(exif_col, ""))

            if dt is None and date_col and time_col:
                date_value = (row.get(date_col) or "").strip()
                time_value = (row.get(time_col) or "").strip()
                if date_value and time_value:
                    if len(date_value) == 8 and date_value.isdigit():
                        date_value = f"{date_value[0:4]}-{date_value[4:6]}-{date_value[6:8]}"
                    dt = parse_datetime_loose(f"{date_value} {time_value}")

            if dt:
                output[file_id] = dt

        return output


def top2(scores):
    values = []
    for score in scores or []:
        try:
            values.append(float(score))
        except Exception:
            pass

    if not values:
        return (0.0, 0.0)

    values.sort(reverse=True)
    p1 = values[0]
    p2 = values[1] if len(values) > 1 else 0.0
    return p1, p2


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


def _is_unresolved_label(label: str, species_level: bool) -> bool:
    normalized = (label or "").strip().lower()
    if normalized in {"blank", "human"}:
        return False
    return not bool(species_level)


def decision_needs_review(label: str, score: float, margin: float, species_level: bool):
    is_blank = label == "blank"
    is_human = label == "human"
    unresolved = _is_unresolved_label(label, species_level)
    threshold = THRESH_GENERIC if unresolved else THRESH_NORMAL

    needs_review = False
    reasons = []

    if is_blank or is_human:
        if score < 0.85:
            needs_review = True
            reasons.append("low_score_for_blank_or_human")
        if margin < 0.10:
            needs_review = True
            reasons.append("low_margin_for_blank_or_human")
    else:
        if score < threshold:
            needs_review = True
            reasons.append(f"low_score<{threshold}")
        if margin < MARGIN_MIN:
            needs_review = True
            reasons.append(f"low_margin<{MARGIN_MIN}")
        if unresolved:
            needs_review = True
            reasons.append("generic_label")

    return needs_review, label, ";".join(reasons) if reasons else "uncertain"


def burst_vote(items: list[dict]) -> tuple[str, bool]:
    for item in items:
        if item["label"] == "human" and item["score"] >= 0.85:
            return "human", False

    blank_weight = sum(item["score"] for item in items if item["label"] == "blank")
    if blank_weight >= 0.85 * max(1, len(items)) * 0.7:
        return "blank", False

    weights = defaultdict(float)
    species_level_by_label = defaultdict(bool)

    for item in items:
        label = item["label"]
        weight = float(item["score"])
        if not item["species_level"] and label not in ("blank", "human"):
            weight *= 0.25
        weights[label] += weight
        species_level_by_label[label] = species_level_by_label[label] or bool(
            item["species_level"]
        )

    if not weights:
        return "animal_unclassified", False

    sorted_items = sorted(weights.items(), key=lambda item: item[1], reverse=True)
    best_label, best_weight = sorted_items[0]

    if not species_level_by_label[best_label]:
        for label, weight in sorted_items[1:]:
            if species_level_by_label[label] and weight >= 0.75 * best_weight:
                return label, True

    return best_label, bool(species_level_by_label[best_label])


def make_bursts(pred_rows, burst_window_seconds: int = BURST_WINDOW_SECONDS):
    burst_window_seconds = max(10, min(300, int(burst_window_seconds)))
    by_folder = defaultdict(list)

    for index, pred_row in enumerate(pred_rows):
        filepath = pred_row["filepath"]
        dt = pred_row.get("dt")
        if dt is None:
            by_folder[(folder_key_from_filepath(filepath), "NO_DT")].append((dt, index))
        else:
            by_folder[folder_key_from_filepath(filepath)].append((dt, index))

    bursts = []
    window = timedelta(seconds=burst_window_seconds)

    for key, rows in by_folder.items():
        if isinstance(key, tuple) and key[1] == "NO_DT":
            for _, index in rows:
                bursts.append([index])
            continue

        rows.sort(key=lambda item: item[0])
        current = []
        last_dt = None

        for dt, index in rows:
            if not current:
                current = [index]
                last_dt = dt
                continue

            if (dt - last_dt) <= window:
                current.append(index)
                last_dt = dt
            else:
                bursts.append(current)
                current = [index]
                last_dt = dt

        if current:
            bursts.append(current)

    return bursts


def postprocess_speciesnet_results(
    in_path: Path = IN_JSON,
    manifest_csv: Path = MANIFEST_CSV,
    metadata_csv: Path = METADATA_CSV,
    out_csv: Path = OUT_CSV,
    review_csv: Path = REVIEW_CSV,
    burst_window_seconds: int = BURST_WINDOW_SECONDS,
) -> dict:
    burst_window_seconds = max(10, min(300, int(burst_window_seconds)))

    in_path = Path(in_path)
    manifest_csv = Path(manifest_csv)
    metadata_csv = Path(metadata_csv)
    out_csv = Path(out_csv)
    review_csv = Path(review_csv)

    if not in_path.exists() and MOUNTED_JSON.exists():
        in_path = MOUNTED_JSON
    if not in_path.exists():
        raise FileNotFoundError(
            f"Missing input JSON: {in_path} (also checked {MOUNTED_JSON})"
        )

    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    predictions = data if isinstance(data, list) else data.get("predictions", [])

    fileid_to_path = load_manifest_localpath_by_fileid(manifest_csv)
    fileid_to_dt = load_exif_dt_by_fileid(metadata_csv)

    exact_path_to_dt = {}
    basename_to_candidates = defaultdict(list)
    tail_to_dt = {}

    for file_id, dt in fileid_to_dt.items():
        local_path = fileid_to_path.get(file_id)
        if not local_path:
            continue

        normalized_path = normalize_path(local_path)
        exact_path_to_dt[normalized_path] = dt

        basename = PurePosixPath(normalized_path).name
        if basename:
            basename_to_candidates[basename].append((normalized_path, dt))

        for n_parts in (3, 4, 5):
            tail_to_dt[tail_key(normalized_path, n_parts)] = dt

    def lookup_dt(filepath: str):
        normalized_path = normalize_path(filepath)
        if not normalized_path:
            return None

        if normalized_path in exact_path_to_dt:
            return exact_path_to_dt[normalized_path]

        for n_parts in (3, 4, 5):
            key = tail_key(normalized_path, n_parts)
            if key in tail_to_dt:
                return tail_to_dt[key]

        basename = PurePosixPath(normalized_path).name
        candidates = basename_to_candidates.get(basename, [])
        if len(candidates) == 1:
            return candidates[0][1]

        folder = folder_key_from_filepath(normalized_path)
        for full_path, dt in candidates:
            if folder_key_from_filepath(full_path) == folder:
                return dt

        return None

    pred_rows = []
    for prediction in predictions:
        filepath = normalize_path(prediction.get("filepath", ""))
        raw_score = safe_float(prediction.get("prediction_score", 0.0), 0.0)

        detections = prediction.get("detections") or []
        has_animal = _count_detections(detections, ANIMAL_CATEGORY, DETECTION_THRESHOLD) > 0
        has_human = _count_detections(detections, PERSON_CATEGORY, DETECTION_THRESHOLD) > 0
        resolved = resolve_prediction(
            prediction,
            has_animal=has_animal,
            has_human=has_human,
        )

        classification_scores = (
            (prediction.get("classifications") or {}).get("scores", []) or []
        )
        p1, p2 = top2(classification_scores)
        margin = p1 - p2

        pred_rows.append(
            {
                "filepath": filepath,
                "label_raw": resolved.get("raw_prediction_label", ""),
                "score": raw_score,
                "resolved_label": resolved.get("resolved_label", ""),
                "resolved_score": safe_float(resolved.get("resolved_score", 0.0), 0.0),
                "resolved_rank": resolved.get("resolved_rank", ""),
                "resolved_species_level": bool(resolved.get("resolved_species_level")),
                "resolved_source": resolved.get("resolved_source", ""),
                "prediction_source": resolved.get("prediction_source", ""),
                "candidate_labels_json": resolved.get("classification_candidates_json", "[]"),
                "margin": margin,
                "is_blank": int(resolved.get("resolved_label") == "blank"),
                "is_human": int(resolved.get("resolved_label") == "human"),
                "dt": lookup_dt(filepath),
            }
        )

    bursts = make_bursts(pred_rows, burst_window_seconds=burst_window_seconds)

    voted_label_by_idx = {}
    voted_species_level_by_idx = {}
    for burst in bursts:
        items = [
            {
                "label": pred_rows[index]["resolved_label"],
                "score": pred_rows[index]["resolved_score"] or pred_rows[index]["score"],
                "species_level": pred_rows[index]["resolved_species_level"],
            }
            for index in burst
        ]
        voted_label, voted_species_level = burst_vote(items)
        for index in burst:
            voted_label_by_idx[index] = voted_label
            voted_species_level_by_idx[index] = voted_species_level

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    review_csv.parent.mkdir(parents=True, exist_ok=True)

    review_count = 0
    generic_review_count = 0

    with open(out_csv, "w", newline="", encoding="utf-8") as f_out, open(
        review_csv, "w", newline="", encoding="utf-8"
    ) as f_review:
        out_writer = csv.DictWriter(
            f_out,
            fieldnames=[
                "filepath",
                "label_raw",
                "score",
                "resolved_label",
                "resolved_score",
                "resolved_rank",
                "resolved_source",
                "p1_minus_p2",
                "burst_label",
                "is_blank",
                "is_human",
                "final_label",
                "needs_review",
                "prediction_source",
                "candidate_labels_json",
            ],
        )
        review_writer = csv.DictWriter(
            f_review,
            fieldnames=[
                "filepath",
                "label_raw",
                "score",
                "resolved_label",
                "resolved_score",
                "resolved_rank",
                "resolved_source",
                "p1_minus_p2",
                "burst_label",
                "final_label",
                "needs_review",
                "reason",
                "prediction_source",
                "candidate_labels_json",
            ],
        )

        out_writer.writeheader()
        review_writer.writeheader()

        for index, row in enumerate(pred_rows):
            score_for_review = row["resolved_score"] or row["score"]
            burst_label = voted_label_by_idx.get(index, row["resolved_label"])
            burst_species_level = voted_species_level_by_idx.get(
                index,
                row["resolved_species_level"],
            )

            needs_review, final_label, reason = decision_needs_review(
                burst_label,
                score_for_review,
                row["margin"],
                burst_species_level,
            )

            out_writer.writerow(
                {
                    "filepath": row["filepath"],
                    "label_raw": row["label_raw"],
                    "score": round(row["score"], 6),
                    "resolved_label": row["resolved_label"],
                    "resolved_score": round(score_for_review, 6),
                    "resolved_rank": row["resolved_rank"],
                    "resolved_source": row["resolved_source"],
                    "p1_minus_p2": round(row["margin"], 6),
                    "burst_label": burst_label,
                    "is_blank": row["is_blank"],
                    "is_human": row["is_human"],
                    "final_label": final_label,
                    "needs_review": int(needs_review),
                    "prediction_source": row["prediction_source"],
                    "candidate_labels_json": row["candidate_labels_json"],
                }
            )

            if needs_review:
                review_count += 1
                if "generic_label" in reason.split(";"):
                    generic_review_count += 1
                review_writer.writerow(
                    {
                        "filepath": row["filepath"],
                        "label_raw": row["label_raw"],
                        "score": round(row["score"], 6),
                        "resolved_label": row["resolved_label"],
                        "resolved_score": round(score_for_review, 6),
                        "resolved_rank": row["resolved_rank"],
                        "resolved_source": row["resolved_source"],
                        "p1_minus_p2": round(row["margin"], 6),
                        "burst_label": burst_label,
                        "final_label": final_label,
                        "needs_review": 1,
                        "reason": reason,
                        "prediction_source": row["prediction_source"],
                        "candidate_labels_json": row["candidate_labels_json"],
                    }
                )

    print(f"Wrote: {out_csv}")
    print(f"Wrote: {review_csv}")
    print(f"Burst window: {burst_window_seconds}s")
    print(f"Total predictions: {len(pred_rows)}")
    print(f"Total bursts: {len(bursts)}")
    print(f"Review items: {review_count}")
    print(f"Generic label review items: {generic_review_count}")

    return {
        "results_csv": str(out_csv),
        "review_csv": str(review_csv),
        "total_predictions": len(pred_rows),
        "total_bursts": len(bursts),
        "review_items": review_count,
        "generic_label_review_items": generic_review_count,
        "burst_window_seconds": burst_window_seconds,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in_path", default=str(IN_JSON))
    parser.add_argument("--manifest_csv", default=str(MANIFEST_CSV))
    parser.add_argument("--metadata_csv", default=str(METADATA_CSV))
    parser.add_argument("--out_csv", default=str(OUT_CSV))
    parser.add_argument("--review_csv", default=str(REVIEW_CSV))
    parser.add_argument("--burst_window", type=int, default=300)
    args = parser.parse_args()

    postprocess_speciesnet_results(
        in_path=Path(args.in_path),
        manifest_csv=Path(args.manifest_csv),
        metadata_csv=Path(args.metadata_csv),
        out_csv=Path(args.out_csv),
        review_csv=Path(args.review_csv),
        burst_window_seconds=args.burst_window,
    )


if __name__ == "__main__":
    main()
