from __future__ import annotations

from typing import Optional

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pipeline.review_decisions import (
    REVIEW_DECISIONS_CSV,
    load_review_decisions,
    normalize_review_path,
)
from scripts.pipeline.simple_outputs import (
    ANIMAL_RESULTS_CSV,
    FINAL_RESULTS_CSV,
    REVIEW_NEEDED_CSV,
    SUMMARY_BY_CAMERA_CSV,
    write_simple_outputs,
)


MANIFEST = Path("data/outputs/manifest.csv")
META = Path("data/outputs/metadata.csv")
DRIVE_INDEX = Path("data/outputs/drive_index.csv")
SPECIESNET_RESULTS = Path("data/outputs/speciesnet_results.csv")

OUT_DIR = Path("data/outputs/by_location")
ANIMAL_UNCLASSIFIED = "animal_unclassified"
ALL_RESULTS_CSV = "all_results.csv"
ANIMAL_REVIEW_CSV = "animal_unclassified.csv"
EXCLUDED_REVIEW_CSV = "excluded_non_animal.csv"

NON_ANIMAL_SPECIES = {"", "blank", "human", "vehicle", "no cv result"}
NON_SPECIES_GROUPS = {
    ANIMAL_UNCLASSIFIED,
    "animal",
    "mammal",
    "bird",
    "rodent",
    "rabbit",
    "squirrel",
    "deer",
    "fox",
    "canis species",
    "canine family",
    "carnivorous mammal",
    "unknown",
    "unknown mammal",
}


def load_csv_by_key(path: Path, key: str) -> dict:
    output = {}
    if not path.exists():
        return output
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            value = (row.get(key, "") or "").strip()
            if value:
                output[value] = row
    return output


def _path_lookup_keys(*values: str) -> set[str]:
    keys = set()
    for value in values:
        text = (value or "").strip()
        if not text:
            continue
        keys.add(text)
        keys.add(text.replace("\\", "/"))
        try:
            path = Path(text)
            keys.add(path.name)
            keys.add(str(path))
            keys.add(str(path.resolve()))
        except Exception:
            pass
    return {key for key in keys if key}


def load_speciesnet_results(path: Path = SPECIESNET_RESULTS) -> dict[str, dict]:
    """Load postprocessed resolved labels keyed by path and filename."""
    lookup: dict[str, dict] = {}
    if not path.exists():
        return lookup

    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for key in _path_lookup_keys(
                row.get("filepath", ""),
                row.get("local_path", ""),
                row.get("file_name", ""),
                row.get("local_file_name", ""),
            ):
                lookup[key] = row
    return lookup


def lookup_speciesnet_result(lookup: dict[str, dict], *values: str) -> dict:
    for key in _path_lookup_keys(*values):
        if key in lookup:
            return lookup[key]
    return {}


def _apply_resolved_prediction(metadata_row: dict, prediction_row: dict) -> dict:
    """Overlay SpeciesNet postprocess fields onto metadata for output routing.

    ``metadata.csv`` can legitimately contain top-level ``species=blank`` when
    model output was rolled up to a broad taxonomy group. The postprocess CSV's
    ``final_label`` / ``resolved_label`` is the resolved field the UI and simple
    CSVs should use.
    """
    if not prediction_row:
        return metadata_row

    out = dict(metadata_row)
    label = (
        prediction_row.get("final_label")
        or prediction_row.get("resolved_label")
        or prediction_row.get("label_raw")
        or ""
    ).strip()
    normalized_label = _normalize_species(label)
    is_blank = _parse_bool(prediction_row.get("is_blank"))
    is_human = _parse_bool(prediction_row.get("is_human")) or normalized_label == "human"
    is_vehicle = normalized_label == "vehicle"

    if normalized_label:
        out["species"] = normalized_label
        out["species_raw"] = (
            prediction_row.get("resolved_label")
            or prediction_row.get("final_label")
            or prediction_row.get("label_raw")
            or out.get("species_raw", "")
        )
    if prediction_row.get("resolved_score") or prediction_row.get("score"):
        out["model_certainty"] = (
            prediction_row.get("resolved_score")
            or prediction_row.get("score")
            or out.get("model_certainty", "")
        )
    if prediction_row.get("prediction_source") or prediction_row.get("resolved_source"):
        out["prediction_source"] = (
            prediction_row.get("prediction_source")
            or prediction_row.get("resolved_source")
            or out.get("prediction_source", "")
        )
        out["resolved_source"] = (
            prediction_row.get("resolved_source")
            or prediction_row.get("prediction_source")
            or out.get("resolved_source", "")
        )
    if prediction_row.get("resolved_rank"):
        out["species_rank"] = prediction_row.get("resolved_rank", "")

    if is_human:
        out["has_animal"] = "0"
        out["has_human"] = "1"
    elif is_blank or is_vehicle or normalized_label in {"", "blank", "no cv result"}:
        out["has_animal"] = "0"
        out["has_human"] = out.get("has_human", "0") or "0"
    else:
        out["has_animal"] = "1"
        out["has_human"] = "0"
        out["species_level"] = "1"
        out["count"] = out.get("count") or out.get("animal_count") or "1"

    return out


def extract_image_number(filename: str) -> str:
    match = re.search(r"(IMG)_?(\d+)", filename, re.IGNORECASE)
    if match:
        num = match.group(2).zfill(4)
        return f"IMG_{num}"
    return filename


def _normalize_camera_label(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "Unknown"
    name = re.sub(r"^\d{4}_\d{2}_\d{2}_", "", name)
    name = re.sub(r"_DONE$", "", name, flags=re.IGNORECASE)
    name = name.replace(" ", "")
    return name or "Unknown"


def get_camera_name(drive_row: dict, manifest_row: Optional[dict] = None) -> str:
    deployment_folder = (drive_row.get("deployment_folder") or "").strip()
    site = (drive_row.get("site") or "").strip()

    if deployment_folder:
        return _normalize_camera_label(deployment_folder)

    if site:
        return _normalize_camera_label(site)

    if manifest_row:
        local_path = (manifest_row.get("local_path") or "").strip()
        if local_path:
            parent_name = Path(local_path).parent.name.strip()
            if parent_name and parent_name not in {"", ".", "staging", "data"}:
                return _normalize_camera_label(parent_name)

    return "Unknown"


def format_date(exif_datetime: str) -> str:
    if not exif_datetime:
        return ""
    try:
        date_part = exif_datetime.split(" ")[0]
        return re.sub(r"[^0-9]", "", date_part)
    except Exception:
        return ""


def format_time(exif_datetime: str) -> str:
    if not exif_datetime:
        return ""
    try:
        parts = exif_datetime.split(" ")
        if len(parts) > 1:
            return parts[1]
    except Exception:
        pass
    return ""


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name)
    cleaned = cleaned.strip().strip(".")
    return cleaned or "Unknown"


def _normalize_species(value: str) -> str:
    text = (value or "").strip().lower().replace("_", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.replace(" ", "_") if text == "animal unclassified" else text

def _display_species_name(species: str) -> tuple[str, str]:
    normalized = _normalize_species(species)

    if normalized in {"eastern cottontail", "european rabbit", "rabbit"}:
        return "rabbit", ""

    if normalized in {"northern raccoon", "raccoon"}:
        return "raccoon", ""

    if normalized == "wild boar":
        return "coyote", "raw_model_label=wild boar; display_species_overridden_to=coyote"

    return normalized, ""


def _parse_bool(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_date_token(value: str) -> str:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    if len(digits) == 8:
        return digits
    return ""


def _normalize_time_token(value: str) -> str:
    text = (value or "").strip()
    if re.match(r"^\d{2}:\d{2}:\d{2}$", text):
        return text
    return ""


def _parse_row_dt(date_value: str, time_value: str):
    normalized_date = _normalize_date_token(date_value)
    normalized_time = _normalize_time_token(time_value)
    if not normalized_date or not normalized_time:
        return None
    try:
        return datetime(
            int(normalized_date[0:4]),
            int(normalized_date[4:6]),
            int(normalized_date[6:8]),
            int(normalized_time[0:2]),
            int(normalized_time[3:5]),
            int(normalized_time[6:8]),
        )
    except Exception:
        return None


def _is_resolved_species(species: str, species_level: Optional[bool] = None, species_rank: str = "") -> bool:
    normalized = _normalize_species(species)
    if not normalized or normalized in NON_ANIMAL_SPECIES:
        return False
    if species_level is not None:
        return bool(species_level)
    if species_rank == "species_binomial":
        return True
    return normalized not in NON_SPECIES_GROUPS


def _load_species_records(metadata_row: dict, review_decision: Optional[dict]) -> list[dict]:
    records_json = (metadata_row.get("species_records_json") or "").strip()
    records = []

    if records_json:
        try:
            parsed = json.loads(records_json)
            if isinstance(parsed, list):
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    species = _normalize_species(item.get("species", ""))
                    if not species:
                        continue
                    records.append(
                        {
                            "species": species,
                            "species_raw": (item.get("species_raw") or "").strip(),
                            "model_certainty": item.get("model_certainty", ""),
                            "prediction_source": (item.get("prediction_source") or "").strip(),
                            "species_rank": (item.get("species_rank") or "").strip(),
                            "species_level": _parse_bool(item.get("species_level")),
                            "count": _safe_int(
                                item.get("count"),
                                _safe_int(metadata_row.get("count"), 1),
                            ),
                        }
                    )
        except json.JSONDecodeError:
            records = []

    if not records:
        species = _normalize_species(metadata_row.get("species", ""))
        if species:
            records = [
                {
                    "species": species,
                    "species_raw": (metadata_row.get("species_raw") or "").strip(),
                    "model_certainty": metadata_row.get("model_certainty", ""),
                    "prediction_source": (metadata_row.get("resolved_source") or metadata_row.get("prediction_source") or "").strip(),
                    "species_rank": (metadata_row.get("species_rank") or "").strip(),
                    "species_level": _parse_bool(metadata_row.get("species_level")),
                    "count": _safe_int(
                        metadata_row.get("count"),
                        _safe_int(metadata_row.get("animal_count"), 1),
                    ),
                }
            ]

    if review_decision and review_decision.get("reviewed_species"):
        reviewed_species = _normalize_species(review_decision.get("reviewed_species", ""))
        if reviewed_species:
            records = [
                {
                    "species": reviewed_species,
                    "species_raw": (metadata_row.get("species_raw") or reviewed_species).strip(),
                    "model_certainty": metadata_row.get("model_certainty", ""),
                    "prediction_source": "manual_review",
                    "species_rank": "manual_review",
                    "species_level": _is_resolved_species(reviewed_species),
                    "count": max(
                        1,
                        _safe_int(metadata_row.get("animal_count"), 0)
                        or _safe_int(metadata_row.get("count"), 1),
                    ),
                }
            ]

    return records


def _classify_row(
    *,
    has_animal: str,
    has_human: str,
    species: str,
    species_level: bool,
) -> str:
    normalized = _normalize_species(species)
    if has_animal == "1":
        if _is_resolved_species(normalized, species_level):
            return "resolved_species"
        return "animal_unclassified"
    if has_human == "1" or normalized == "human":
        return "human"
    if normalized in {"", "blank"}:
        return "blank"
    if normalized in {"vehicle", "no cv result"}:
        return "excluded"
    return "excluded"


def generate_output_csvs(
    manifest: Path = MANIFEST,
    metadata: Path = META,
    drive_index: Path = DRIVE_INDEX,
    out_dir: Path = OUT_DIR,
    burst_seconds: int = 300,
    burst_export: str = "all",
    start_date: str = "",
    end_date: str = "",
    start_time: str = "",
    end_time: str = "",
    filter_mode: str = "auto",
    offset_start_date: str = "",
    offset_end_date: str = "",
    offset_start_time: str = "",
    offset_end_time: str = "",
    shift_minutes: int = 0,
    set_year: Optional[int] = None,
    set_month: Optional[int] = None,
    set_day: Optional[int] = None,
    offset_apply_to: str = "both",
    exclude_humans: bool = False,
    review_decisions_path: Path = REVIEW_DECISIONS_CSV,
) -> dict:
    args = argparse.Namespace(
        manifest=str(manifest),
        metadata=str(metadata),
        drive_index=str(drive_index),
        out_dir=str(out_dir),
        burst_seconds=burst_seconds,
        burst_export=burst_export,
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        end_time=end_time,
        filter_mode=filter_mode,
        offset_start_date=offset_start_date,
        offset_end_date=offset_end_date,
        offset_start_time=offset_start_time,
        offset_end_time=offset_end_time,
        shift_minutes=shift_minutes,
        set_year=set_year,
        set_month=set_month,
        set_day=set_day,
        offset_apply_to=offset_apply_to,
        exclude_humans=exclude_humans,
    )
    args.burst_seconds = max(10, min(300, int(args.burst_seconds)))

    manifest_path = Path(args.manifest)
    meta_path = Path(args.metadata)
    drive_index_path = Path(args.drive_index)
    out_dir = Path(args.out_dir)

    if not manifest_path.exists():
        raise FileNotFoundError("manifest.csv not found. Run make_manifest.py first.")
    if not meta_path.exists():
        raise FileNotFoundError("metadata.csv not found. Run extract_metadata.py first.")

    manifest_by_id = load_csv_by_key(manifest_path, "file_id")
    meta_by_id = load_csv_by_key(meta_path, "file_id")
    meta_by_path = load_csv_by_key(meta_path, "local_path")
    meta_by_local_name = load_csv_by_key(meta_path, "local_file_name")
    meta_by_file_name = load_csv_by_key(meta_path, "file_name")
    speciesnet_by_path = load_speciesnet_results(SPECIESNET_RESULTS)
    drive_by_id = (
        load_csv_by_key(drive_index_path, "file_id") if drive_index_path.exists() else {}
    )
    review_decisions = load_review_decisions(review_decisions_path)

    start_date = _normalize_date_token(args.start_date)
    end_date = _normalize_date_token(args.end_date)
    start_time = _normalize_time_token(args.start_time)
    end_time = _normalize_time_token(args.end_time)

    offset_start_date = _normalize_date_token(args.offset_start_date)
    offset_end_date = _normalize_date_token(args.offset_end_date)
    offset_start_time = _normalize_time_token(args.offset_start_time) or "00:00:00"
    offset_end_time = _normalize_time_token(args.offset_end_time) or "23:59:59"

    total_flagged_outside_interval = 0
    total_missing_datetime_for_interval = 0
    total_processed = 0
    total_excluded_humans = 0
    bucket_counts = defaultdict(int)

    rows_by_camera = defaultdict(list)
    combined_rows = []
    animal_unclassified_rows = []
    non_animal_rows = []

    offset_enabled = bool(offset_start_date and offset_end_date) and (
        args.shift_minutes != 0
        or args.set_year is not None
        or args.set_month is not None
        or args.set_day is not None
    )

    offset_start_dt = _parse_row_dt(offset_start_date, offset_start_time) if offset_enabled else None
    offset_end_dt = _parse_row_dt(offset_end_date, offset_end_time) if offset_enabled else None
    if (
        offset_enabled
        and (offset_start_dt is None or offset_end_dt is None or offset_end_dt < offset_start_dt)
    ):
        offset_enabled = False

    FINAL_FIELDS = [
        "CameraName",
        "DeploymentFolder",
        "Image#",
        "Species",
        "# of Individuals",
        "CorrectedSpecies",
        "Corrected# of Individuals",
        "HasMultipleSpecies",
        "SecondarySpecies",
        "Secondary# of Individuals",
        "Date",
        "Time",
        "CorrectedDate",
        "CorrectedTime",
        "ObservationID",
        "BurstCount",
        "BurstIndex",
        "has_animal",
        "has_human",
        "model_certainty",
        "RawSpeciesLabel",
        "PredictionSource",
        "ReviewStatus",
        "ReviewReason",
        "Notes",
    ]

    with open(manifest_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            file_id = (row.get("file_id") or "").strip()
            filename = (row.get("file_name") or row.get("local_file_name") or "").strip()

            manifest_row = manifest_by_id.get(file_id, row) if file_id else row
            manifest_local_path = (
                manifest_row.get("local_path") or row.get("local_path") or ""
            ).strip()
            manifest_local_name = (
                manifest_row.get("local_file_name")
                or row.get("local_file_name")
                or filename
            ).strip()
            metadata_row = (
                (meta_by_id.get(file_id) if file_id else None)
                or meta_by_path.get(manifest_local_path)
                or meta_by_local_name.get(manifest_local_name)
                or meta_by_file_name.get(filename)
                or {}
            )
            prediction_row = lookup_speciesnet_result(
                speciesnet_by_path,
                manifest_local_path,
                metadata_row.get("local_path", ""),
                manifest_local_name,
                filename,
            )
            metadata_row = _apply_resolved_prediction(metadata_row, prediction_row)
            drive_row = drive_by_id.get(file_id, {})

            total_processed += 1

            local_path = (
                metadata_row.get("local_path")
                or manifest_row.get("local_path")
                or row.get("local_path")
                or ""
            ).strip()
            review_decision = review_decisions.get(normalize_review_path(local_path))

            has_animal = (metadata_row.get("has_animal", "") or "").strip()
            has_human = (metadata_row.get("has_human", "") or "").strip()

            if exclude_humans and has_human == "1" and has_animal != "1":
                total_excluded_humans += 1
                continue

            camera_name = get_camera_name(drive_row, manifest_row)
            deployment_folder = (drive_row.get("deployment_folder") or "").strip()
            image_num = extract_image_number(filename)

            date_value = (metadata_row.get("date", "") or "").strip()
            time_value = (metadata_row.get("time", "") or "").strip()
            if not _normalize_date_token(date_value) or not _normalize_time_token(time_value):
                exif_dt = (metadata_row.get("exif_datetime", "") or "").strip()
                if not _normalize_date_token(date_value):
                    date_value = format_date(exif_dt)
                if not _normalize_time_token(time_value):
                    time_value = format_time(exif_dt)

            notes_value = ""
            compare_date = _normalize_date_token(date_value)
            compare_time = _normalize_time_token(time_value)

            if start_date or end_date or start_time or end_time:
                if not compare_date or not compare_time:
                    total_missing_datetime_for_interval += 1
                    notes_value = "WARNING: Missing date/time for interval check"
                else:
                    outside = False
                    if start_date and compare_date < start_date:
                        outside = True
                    if end_date and compare_date > end_date:
                        outside = True
                    if start_date and end_date and start_date == end_date:
                        if start_time and compare_time < start_time:
                            outside = True
                        if end_time and compare_time > end_time:
                            outside = True
                    else:
                        if start_date and compare_date == start_date and start_time and compare_time < start_time:
                            outside = True
                        if end_date and compare_date == end_date and end_time and compare_time > end_time:
                            outside = True

                    if outside:
                        total_flagged_outside_interval += 1
                        notes_value = "WARNING: Date/time outside deployment interval"

            corrected_date = ""
            corrected_time = ""
            if offset_enabled:
                row_dt = _parse_row_dt(compare_date, compare_time)
                if row_dt is not None and offset_start_dt is not None and offset_end_dt is not None:
                    if offset_start_dt <= row_dt <= offset_end_dt:
                        new_dt = row_dt
                        try:
                            year = args.set_year if args.set_year is not None else new_dt.year
                            month = args.set_month if args.set_month is not None else new_dt.month
                            day = args.set_day if args.set_day is not None else new_dt.day
                            new_dt = new_dt.replace(year=year, month=month, day=day)
                        except Exception:
                            pass

                        if args.shift_minutes != 0:
                            try:
                                new_dt = new_dt + timedelta(minutes=int(args.shift_minutes))
                            except Exception:
                                pass

                        new_date = f"{new_dt.year:04d}{new_dt.month:02d}{new_dt.day:02d}"
                        new_time = f"{new_dt.hour:02d}:{new_dt.minute:02d}:{new_dt.second:02d}"

                        if args.offset_apply_to == "date":
                            corrected_date = new_date
                            date_value = corrected_date
                        elif args.offset_apply_to == "time":
                            corrected_time = new_time
                            time_value = corrected_time
                        else:
                            corrected_date = new_date
                            corrected_time = new_time
                            date_value = corrected_date
                            time_value = corrected_time

                        notes_value = (
                            f"{notes_value}; OFFSET_APPLIED".strip("; ").strip()
                            if notes_value
                            else "OFFSET_APPLIED"
                        )

            review_status = (review_decision or {}).get("review_status", "")
            review_reason = (review_decision or {}).get("review_reason", "")
            species_records = _load_species_records(metadata_row, review_decision)

            if not species_records:
                species_records = [
                    {
                        "species": _normalize_species(metadata_row.get("species", "")),
                        "species_raw": (metadata_row.get("species_raw") or "").strip(),
                        "model_certainty": metadata_row.get("model_certainty", ""),
                        "prediction_source": (metadata_row.get("resolved_source") or metadata_row.get("prediction_source") or "").strip(),
                        "species_rank": (metadata_row.get("species_rank") or "").strip(),
                        "species_level": _parse_bool(metadata_row.get("species_level")),
                        "count": _safe_int(metadata_row.get("count"), 0),
                    }
                ]

            visible_species_records = [
                record for record in species_records if record.get("species") or has_animal == "1"
            ]

            image_key = file_id or local_path or filename
            multiple_species = len(
                [
                    record
                    for record in visible_species_records
                    if _classify_row(
                        has_animal=has_animal,
                        has_human=has_human,
                        species=record.get("species", ""),
                        species_level=bool(record.get("species_level")),
                    )
                    in {"resolved_species", "animal_unclassified"}
                ]
            ) > 1

            for record in visible_species_records:
                species = _normalize_species(record.get("species", ""))
                display_species, species_note = _display_species_name(species)
                if display_species:
                    species = display_species

                species_level = bool(record.get("species_level"))
                row_bucket = _classify_row(
                    has_animal=has_animal,
                    has_human=has_human,
                    species=species,
                    species_level=species_level,
                )

                if row_bucket == "blank" and not species:
                    species = "blank"
                elif row_bucket == "human" and not species:
                    species = "human"
                elif row_bucket == "animal_unclassified" and not species:
                    species = ANIMAL_UNCLASSIFIED
                
                secondary_species = ""
                if multiple_species:
                    other_display_species = []
                    for other in visible_species_records:
                        other_species = _normalize_species(other.get("species", ""))
                        other_display, _ = _display_species_name(other_species)
                        if other_display and other_display != species:
                            other_display_species.append(other_display)

                    seen = []
                    for item in other_display_species:
                        if item not in seen:
                            seen.append(item)

                    secondary_species = "; ".join(seen)

                count_value = record.get("count") or metadata_row.get("count") or ""
                if not count_value and row_bucket in {"resolved_species", "animal_unclassified"}:
                    count_value = max(
                        1,
                        _safe_int(metadata_row.get("animal_count"), 0)
                        or _safe_int(metadata_row.get("count"), 1),
                    )

                row_data = {
                    "CameraName": camera_name,
                    "DeploymentFolder": deployment_folder,
                    "Image#": image_num,
                    "Species": species,
                    "# of Individuals": count_value,
                    "CorrectedSpecies": "",
                    "Corrected# of Individuals": "",
                    "HasMultipleSpecies": "1" if multiple_species else "",
                    "SecondarySpecies": secondary_species,
                    "Secondary# of Individuals": "",
                    "Date": date_value,
                    "Time": time_value,
                    "CorrectedDate": corrected_date,
                    "CorrectedTime": corrected_time,
                    "ObservationID": "",
                    "BurstCount": "",
                    "BurstIndex": "",
                    "has_animal": has_animal,
                    "has_human": has_human,
                    "model_certainty": record.get("model_certainty", ""),
                    "RawSpeciesLabel": record.get("species_raw", ""),
                    "PredictionSource": record.get("prediction_source", ""),
                    "ReviewStatus": review_status,
                    "ReviewReason": review_reason,
                    "Notes": "; ".join(part for part in [notes_value, species_note] if part),
                    "_image_key": image_key,
                    "_filename": filename,
                    "_timestamp": _parse_row_dt(date_value, time_value),
                }

                if row_bucket == "resolved_species":
                    bucket_counts["resolved_species"] += 1
                    rows_by_camera[camera_name].append(row_data)
                elif row_bucket == "animal_unclassified":
                    bucket_counts["animal_unclassified"] += 1
                    row_data["Notes"] = (
                        f"{row_data.get('Notes', '')}; routed_to_animal_unclassified".strip("; ")
                    )
                    animal_unclassified_rows.append(row_data)
                else:
                    bucket_counts[row_bucket] += 1
                    row_data["Notes"] = (
                        f"{row_data.get('Notes', '')}; routed_to_{row_bucket}".strip("; ")
                    )
                    non_animal_rows.append(row_data)

    out_dir.mkdir(parents=True, exist_ok=True)
    for existing_csv in out_dir.glob("*.csv"):
        existing_csv.unlink()

    total_output = 0

    for camera_name, rows in sorted(rows_by_camera.items()):
        rows.sort(
            key=lambda row: (
                _normalize_date_token(row.get("Date", "")),
                _normalize_time_token(row.get("Time", "")),
                row.get("Image#", ""),
                row.get("_image_key", ""),
                row.get("Species", ""),
            )
        )

        image_groups = []
        current_key = None
        current_rows = []
        for row in rows:
            row_key = row.get("_image_key")
            if current_key is None or row_key != current_key:
                if current_rows:
                    image_groups.append(current_rows)
                current_key = row_key
                current_rows = [row]
            else:
                current_rows.append(row)
        if current_rows:
            image_groups.append(current_rows)

        obs_seq = 0
        kept_rows = []
        image_index = 0

        while image_index < len(image_groups):
            burst_start = image_index
            burst_groups = [image_groups[image_index]]
            burst_start_ts = image_groups[image_index][0].get("_timestamp")
            prev_ts = burst_start_ts
            image_index += 1

            while image_index < len(image_groups):
                next_group = image_groups[image_index]
                next_ts = next_group[0].get("_timestamp")
                if prev_ts is None or next_ts is None:
                    break
                if int((next_ts - prev_ts).total_seconds()) <= args.burst_seconds:
                    burst_groups.append(next_group)
                    prev_ts = next_ts
                    image_index += 1
                else:
                    break

            obs_seq += 1
            burst_count = len(burst_groups)
            obs_date = _normalize_date_token(burst_groups[0][0].get("Date", ""))
            obs_id = f"{camera_name}_{obs_date}_{str(obs_seq).zfill(6)}"

            for burst_index, group_rows in enumerate(burst_groups, start=1):
                for row in group_rows:
                    row["ObservationID"] = obs_id
                    row["BurstCount"] = str(burst_count)
                    row["BurstIndex"] = str(burst_index)

            if args.burst_export == "all":
                selected_groups = burst_groups
            else:
                selected_groups = burst_groups[:1]

            for group_rows in selected_groups:
                kept_rows.extend(group_rows)

        csv_path = out_dir / f"{safe_filename(camera_name)}_results.csv"
        write_csv(csv_path, [{k: row.get(k, "") for k in FINAL_FIELDS} for row in kept_rows], FINAL_FIELDS)

        total_output += len(kept_rows)
        combined_rows.extend(kept_rows)
        print(f"  {camera_name}: {len(kept_rows)} rows -> {csv_path}")

    all_results_path = out_dir / ALL_RESULTS_CSV
    animal_unclassified_path = out_dir / ANIMAL_REVIEW_CSV
    non_animal_path = out_dir / EXCLUDED_REVIEW_CSV

    animal_unclassified_rows.sort(
        key=lambda row: (
            row.get("CameraName", ""),
            _normalize_date_token(row.get("Date", "")),
            _normalize_time_token(row.get("Time", "")),
            row.get("Image#", ""),
            row.get("Species", ""),
        )
    )
    non_animal_rows.sort(
        key=lambda row: (
            row.get("CameraName", ""),
            _normalize_date_token(row.get("Date", "")),
            _normalize_time_token(row.get("Time", "")),
            row.get("Image#", ""),
            row.get("Species", ""),
        )
    )
    combined_rows.sort(
        key=lambda row: (
            row.get("CameraName", ""),
            _normalize_date_token(row.get("Date", "")),
            _normalize_time_token(row.get("Time", "")),
            row.get("Image#", ""),
            row.get("Species", ""),
        )
    )
    write_csv(
        all_results_path,
        [{k: row.get(k, "") for k in FINAL_FIELDS} for row in combined_rows],
        FINAL_FIELDS,
    )
    write_csv(
        animal_unclassified_path,
        [{k: row.get(k, "") for k in FINAL_FIELDS} for row in animal_unclassified_rows],
        FINAL_FIELDS,
    )
    write_csv(
        non_animal_path,
        [{k: row.get(k, "") for k in FINAL_FIELDS} for row in non_animal_rows],
        FINAL_FIELDS,
    )

    species_filled = sum(
        1
        for row in combined_rows
        if _is_resolved_species(row.get("Species", ""))
    )
    animal_count = sum(
        1 for row in combined_rows if (row.get("has_animal", "") or "").strip() == "1"
    )

    print(f"\nTotal: {total_output} species rows across {len(rows_by_camera)} locations")
    print(f"Output directory: {out_dir}")

    if start_date or end_date or start_time or end_time:
        print("\nInterval checks:")
        print(f"  Flagged outside interval: {total_flagged_outside_interval}")
        print(f"  Missing date/time for check: {total_missing_datetime_for_interval}")

    print("\nRow routing:")
    print(f"  Total images processed: {total_processed}")
    print(f"  Resolved species rows: {bucket_counts['resolved_species']}")
    print(f"  Animal unclassified rows: {bucket_counts['animal_unclassified']}")
    print(f"  Blank rows: {bucket_counts['blank']}")
    print(f"  Human rows: {bucket_counts['human']}")
    print(f"  Excluded rows: {bucket_counts['excluded']}")
    if args.exclude_humans:
        print(f"  Excluded human-only rows: {total_excluded_humans}")

    print("\nOutput files:")
    print(f"  all_results.csv rows: {len(combined_rows)}")
    print(f"  Main location CSV rows written: {total_output}")
    print(f"  animal_unclassified.csv rows: {len(animal_unclassified_rows)}")
    print(f"  excluded_non_animal.csv rows: {len(non_animal_rows)}")

    # Always write the three simplified, user-facing CSVs alongside the
    # backend debug files. These are what the frontend lists for download.
    simple_summary = write_simple_outputs(
        out_dir,
        combined_rows,
        animal_unclassified_rows,
        non_animal_rows,
    )
    print("\nUser-facing CSVs (frontend will only show these):")
    print(
        f"  {FINAL_RESULTS_CSV}: {simple_summary['final_results_rows']} rows"
    )
    print(
        f"  {ANIMAL_RESULTS_CSV}: {simple_summary['animal_results_rows']} rows"
    )
    print(
        f"  {REVIEW_NEEDED_CSV}: {simple_summary['review_needed_rows']} rows"
    )
    print(
        f"  {SUMMARY_BY_CAMERA_CSV}: {simple_summary['camera_count']} cameras"
    )

    print("\nDetection fields:")
    print(
        "  \u2713 has_animal \u2014 "
        f"{bucket_counts['resolved_species'] + bucket_counts['animal_unclassified']} animal rows routed"
    )
    print("  \u2713 model_certainty \u2014 confidence scores filled")
    print("  \u2713 # of Individuals \u2014 detection counts filled when available")

    if species_filled > 0:
        print("\nSpeciesNet results:")
        print(f"  \u2713 Species \u2014 {species_filled}/{total_output} classified")
    else:
        print("\nSpecies classification:")
        print("  \u25cb Species not confidently classified yet")

    return {
        "manifest_path": str(manifest_path),
        "metadata_path": str(meta_path),
        "drive_index_path": str(drive_index_path),
        "drive_index_present": drive_index_path.exists(),
        "out_dir": str(out_dir),
        "camera_count": len(rows_by_camera),
        "rows_written": total_output,
        "animals": animal_count,
        "humans": bucket_counts["human"],
        "species_filled": species_filled,
        "resolved_species_rows": bucket_counts["resolved_species"],
        "animal_unclassified_rows": bucket_counts["animal_unclassified"],
        "blank_rows": bucket_counts["blank"],
        "human_rows": bucket_counts["human"],
        "excluded_rows": bucket_counts["excluded"],
        "all_results_path": str(all_results_path),
        "animal_unclassified_path": str(animal_unclassified_path),
        "excluded_rows_path": str(non_animal_path),
        "review_decisions_path": str(Path(review_decisions_path)),
        "excluded_humans": total_excluded_humans,
        "final_results_path": simple_summary["final_results_path"],
        "animal_results_path": simple_summary["animal_results_path"],
        "review_needed_path": simple_summary["review_needed_path"],
        "summary_by_camera_path": simple_summary["summary_by_camera_path"],
        "final_results_rows": simple_summary["final_results_rows"],
        "animal_results_rows": simple_summary["animal_results_rows"],
        "review_needed_rows": simple_summary["review_needed_rows"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--metadata", default=str(META))
    parser.add_argument("--drive_index", default=str(DRIVE_INDEX))
    parser.add_argument("--out_dir", default=str(OUT_DIR))
    parser.add_argument("--burst_seconds", type=int, default=300)
    parser.add_argument("--burst_export", choices=["all", "first"], default="all")
    parser.add_argument("--start_date", default="")
    parser.add_argument("--end_date", default="")
    parser.add_argument("--start_time", default="")
    parser.add_argument("--end_time", default="")
    parser.add_argument("--filter_mode", choices=["auto", "md", "speciesnet", "none"], default="auto")
    parser.add_argument("--offset_start_date", default="")
    parser.add_argument("--offset_end_date", default="")
    parser.add_argument("--offset_start_time", default="")
    parser.add_argument("--offset_end_time", default="")
    parser.add_argument("--shift_minutes", type=int, default=0)
    parser.add_argument("--set_year", type=int, default=None)
    parser.add_argument("--set_month", type=int, default=None)
    parser.add_argument("--set_day", type=int, default=None)
    parser.add_argument("--offset_apply_to", choices=["date", "time", "both"], default="both")
    parser.add_argument("--exclude_humans", action="store_true")
    parser.add_argument("--review_decisions", default=str(REVIEW_DECISIONS_CSV))
    args = parser.parse_args()

    generate_output_csvs(
        manifest=Path(args.manifest),
        metadata=Path(args.metadata),
        drive_index=Path(args.drive_index),
        out_dir=Path(args.out_dir),
        burst_seconds=args.burst_seconds,
        burst_export=args.burst_export,
        start_date=args.start_date,
        end_date=args.end_date,
        start_time=args.start_time,
        end_time=args.end_time,
        filter_mode=args.filter_mode,
        offset_start_date=args.offset_start_date,
        offset_end_date=args.offset_end_date,
        offset_start_time=args.offset_start_time,
        offset_end_time=args.offset_end_time,
        shift_minutes=args.shift_minutes,
        set_year=args.set_year,
        set_month=args.set_month,
        set_day=args.set_day,
        offset_apply_to=args.offset_apply_to,
        exclude_humans=args.exclude_humans,
        review_decisions_path=Path(args.review_decisions),
    )


if __name__ == "__main__":
    main()
