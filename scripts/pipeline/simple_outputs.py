"""Simplified, user-facing CSV exports for the wildlife pipeline.

This module produces three small, clean CSV files for non-technical
researchers, while leaving the existing backend/debug CSVs untouched:

  1. final_results.csv     - the main clean export for researchers
  2. animal_results.csv    - animals-only subset
  3. review_needed.csv     - subset that requires human review
  4. summary_by_camera.csv - per-camera roll-up

Backend/debug CSVs (all_results.csv, animal_unclassified.csv,
excluded_non_animal.csv, per-camera *_results.csv) still get written by
make_output.py so existing validation/dashboard logic keeps working;
they are simply filtered out of the frontend export listing.

The simple CSV schema is intentionally tiny:

  image_name, camera_location, date_time, timestamp_status,
  animal_detected, species, confidence, review_needed

Species labels are normalised to a small fixed vocabulary so researchers
never see raw model labels, taxonomy strings, or debug fields.
"""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Mapping, Optional


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

ANIMAL_UNCLASSIFIED = "animal_unclassified"

# The only species labels that may appear in the user-facing CSVs.
ALLOWED_SPECIES = {
    "coyote",
    "bobcat",
    "deer",
    "raccoon",
    "rabbit",
    "skunk",
    "opossum",
    "rodent",
    "bird",
    "human",
    "dog",
    "cat",
    "vehicle",
    "blank",
    ANIMAL_UNCLASSIFIED,
}

# Rows are flagged for review when model_certainty falls below this.
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.70


# ---------------------------------------------------------------------------
# Filenames + columns
# ---------------------------------------------------------------------------

FINAL_RESULTS_CSV = "final_results.csv"
ANIMAL_RESULTS_CSV = "animal_results.csv"
REVIEW_NEEDED_CSV = "review_needed.csv"
SUMMARY_BY_CAMERA_CSV = "summary_by_camera.csv"

# Order matters: `final_results.csv` is the primary export. `animal_results`
# sits next to it so researchers can grab the animals-only subset easily.
USER_FACING_FILENAMES_ORDERED = (
    FINAL_RESULTS_CSV,
    ANIMAL_RESULTS_CSV,
    REVIEW_NEEDED_CSV,
    SUMMARY_BY_CAMERA_CSV,
)

# The full set of "show this to the user" filenames the frontend should list.
USER_FACING_FILENAMES = frozenset(USER_FACING_FILENAMES_ORDERED)

# Friendly display labels for the four frontend files.
USER_FACING_DISPLAY_LABELS = {
    FINAL_RESULTS_CSV: "Final results",
    ANIMAL_RESULTS_CSV: "Animal detections only",
    REVIEW_NEEDED_CSV: "Needs review",
    SUMMARY_BY_CAMERA_CSV: "Summary by camera",
}

FINAL_RESULTS_COLUMNS = [
    "image_name",
    "camera_location",
    "date_time",
    "timestamp_status",
    "animal_detected",
    "species",
    "confidence",
    "review_needed",
]

SUMMARY_COLUMNS = [
    "camera_location",
    "total_images",
    "animals_detected",
    "review_needed",
    "top_species",
]


# ---------------------------------------------------------------------------
# Species normalisation
# ---------------------------------------------------------------------------

# Keyword-based mapping from raw labels (model output / taxonomy strings) to
# the allowed simple labels. Order matters: more specific rules first.
_SPECIES_KEYWORD_RULES: List[tuple] = [
    (("coyote", "canis latrans", "golden jackal", "grey wolf", "gray wolf", "fox"), "coyote"),
    (("bobcat", "lynx rufus"), "bobcat"),
    (("opossum", "didelphis"), "opossum"),
    (("raccoon", "procyon"), "raccoon"),
    (("skunk", "mephitis", "spilogale"), "skunk"),
    (
        ("deer", "odocoileus", "cervus", "elk", "moose", "buck", "doe", "fawn"),
        "deer",
    ),
    (
        (
            "rabbit",
            "cottontail",
            "sylvilagus",
            "lepus",
            "hare",
            "leporidae",
        ),
        "rabbit",
    ),
    (
        (
            "rodent",
            "rat",
            "mouse",
            "mice",
            "vole",
            "woodrat",
            "squirrel",
            "chipmunk",
            "gopher",
            "rodentia",
            "sciuridae",
            "neotoma",
            "peromyscus",
        ),
        "rodent",
    ),
    (("dog", "canis familiaris", "domestic dog"), "dog"),
    (("cat", "felis catus", "domestic cat", "house cat"), "cat"),
    (("human", "person", "people", "homo sapiens"), "human"),
    (("vehicle", "car", "truck", "atv"), "vehicle"),
    (
        (
            "bird",
            "aves",
            "towhee",
            "sparrow",
            "hawk",
            "owl",
            "crow",
            "raven",
            "jay",
            "wren",
            "finch",
            "robin",
            "quail",
            "warbler",
            "vulture",
            "eagle",
            "falcon",
            "duck",
            "goose",
            "heron",
            "egret",
            "thrush",
            "chickadee",
            "starling",
            "blackbird",
            "kingfisher",
            "magpie",
            "dove",
            "pigeon",
            "swallow",
            "hummingbird",
            "phoebe",
            "mockingbird",
            "woodpecker",
        ),
        "bird",
    ),
]

# Labels that explicitly mean "no detection".
_BLANK_TOKENS = {"", "blank", "no cv result", "empty", "none", "no detection"}

# Labels that mean "animal present but species unknown".
_UNCLASSIFIED_TOKENS = {
    "animal",
    "mammal",
    "unknown",
    "unknown mammal",
    "carnivorous mammal",
    "canine family",
    "canis species",
    "animal unclassified",
    ANIMAL_UNCLASSIFIED,
}


def normalize_species(raw_label: str) -> str:
    """Map any raw species label to one of the allowed simple labels.

    Handles common-name variants ("northern raccoon" -> "raccoon"),
    comma-suffix forms ("raccoon, northern" -> "raccoon"), scientific
    names ("Canis latrans" -> "coyote"), and verbose model labels.

    Returns an empty string only when the input is empty/blank-ish.
    Unrecognised animal labels fall back to "animal_unclassified".
    """
    text = (raw_label or "").strip().lower().replace("_", " ")
    text = re.sub(r"[,/;]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if text in _BLANK_TOKENS:
        return "blank" if text else ""

    if text in _UNCLASSIFIED_TOKENS:
        return ANIMAL_UNCLASSIFIED

    for keywords, label in _SPECIES_KEYWORD_RULES:
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", text):
                return label

    # Animal-ish but unrecognised — surface it for review.
    return ANIMAL_UNCLASSIFIED


# ---------------------------------------------------------------------------
# Date / time helpers
# ---------------------------------------------------------------------------

def _parse_date_parts(date_value: str) -> Optional[tuple]:
    digits = re.sub(r"[^0-9]", "", str(date_value or ""))
    if len(digits) != 8:
        return None
    try:
        return int(digits[0:4]), int(digits[4:6]), int(digits[6:8])
    except Exception:
        return None


def _is_time_well_formed(time_value: str) -> bool:
    return bool(re.match(r"^\d{2}:\d{2}:\d{2}$", str(time_value or "").strip()))


def classify_timestamp(date_value: str, time_value: str, notes: str = "") -> str:
    """Return one of 'valid', 'missing', 'odd_timestamp'."""
    date_parts = _parse_date_parts(date_value)
    time_ok = _is_time_well_formed(time_value)

    if not date_parts or not time_ok:
        return "missing"

    year, month, day = date_parts
    current_year = datetime.now().year
    if year < 1990 or year > current_year + 1:
        return "odd_timestamp"
    try:
        datetime(year, month, day)
    except ValueError:
        return "odd_timestamp"

    notes_lower = (notes or "").lower()
    if "outside deployment interval" in notes_lower:
        return "odd_timestamp"

    return "valid"


def format_date_time(date_value: str, time_value: str) -> str:
    """Format ('20260419', '08:00:00') as '2026-04-19 08:00:00'."""
    date_parts = _parse_date_parts(date_value)
    if not date_parts:
        return ""
    year, month, day = date_parts
    formatted_date = f"{year:04d}-{month:02d}-{day:02d}"
    formatted_time = time_value.strip() if _is_time_well_formed(time_value) else "00:00:00"
    return f"{formatted_date} {formatted_time}"


# ---------------------------------------------------------------------------
# Row building
# ---------------------------------------------------------------------------

def _to_confidence(value) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _first_value(row: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _is_truthy(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _simplify_row(
    row: Mapping[str, str],
    *,
    low_confidence_threshold: float,
) -> dict:
    image_name = _first_value(row, "_filename", "Image#", "image_name", "file_name", "local_file_name")
    camera = _first_value(row, "CameraName", "camera_location", "camera", "site") or "Unknown"
    date_value = _first_value(row, "Date", "date")
    time_value = _first_value(row, "Time", "time")
    notes = _first_value(row, "Notes", "notes")

    timestamp_status = classify_timestamp(date_value, time_value, notes)
    has_animal = _is_truthy(_first_value(row, "has_animal", "animal_detected"))

    raw_species = _first_value(row, "Species", "species", "final_label", "resolved_label")
    normalized_species = normalize_species(raw_species)
    raw_confidence = _first_value(row, "model_certainty", "confidence", "resolved_score", "score")
    confidence_raw = _to_confidence(raw_confidence)
    raw_certainty = str(raw_confidence or "").strip()
    individuals = _safe_int(_first_value(row, "# of Individuals", "count", "animal_count"))

    prediction_source = _first_value(row, "PredictionSource", "prediction_source", "resolved_source")
    is_human_reviewed = "manual_review" in prediction_source.lower()

    if is_human_reviewed:
        human_species = (raw_species or "").strip()
        if not human_species:
            normalized_species = ""
        else:
            normalized_species = human_species.lower()
    else:
        normalized_species = normalize_species(raw_species)

    if is_human_reviewed and normalized_species and normalized_species not in {"blank", ""}:
        if normalized_species == "human":
            animal_detected = "no"
            species = "human"
            confidence = round(confidence_raw, 2) if confidence_raw else 1.00
        elif normalized_species == "vehicle":
            animal_detected = "no"
            species = "vehicle"
            confidence = round(confidence_raw, 2) if confidence_raw else 1.00
        else:
            animal_detected = "yes"
            species = normalized_species
            confidence = round(confidence_raw, 2) if confidence_raw else 1.00
    elif normalized_species == "human":
        animal_detected = "no"
        species = "human"
        confidence = 0.00
    elif normalized_species == "vehicle":
        animal_detected = "no"
        species = "vehicle"
        confidence = 0.00
    elif has_animal:
        animal_detected = "yes"
        species = normalized_species or ANIMAL_UNCLASSIFIED
        confidence = round(confidence_raw, 2)
    else:
        animal_detected = "no"
        species = "blank"
        confidence = 0.00

    low_conf = animal_detected == "yes" and confidence_raw < low_confidence_threshold and not is_human_reviewed
    unclassified = species == ANIMAL_UNCLASSIFIED and not is_human_reviewed
    bad_timestamp = timestamp_status in {"missing", "odd_timestamp"}
    review_needed = "yes" if (low_conf or unclassified or bad_timestamp) else "no"

    return {
        "image_name": image_name,
        "camera_location": camera,
        "date_time": format_date_time(date_value, time_value),
        "timestamp_status": timestamp_status,
        "animal_detected": animal_detected,
        "species": species,
        "confidence": f"{confidence:.2f}",
        "review_needed": review_needed,
    }


def build_simple_rows(
    combined_rows: Iterable[Mapping[str, str]],
    animal_unclassified_rows: Iterable[Mapping[str, str]] = (),
    non_animal_rows: Iterable[Mapping[str, str]] = (),
    *,
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
) -> List[dict]:
    """Project internal pipeline rows onto the simple user-facing schema.

    Duplicate (image, camera, species, date, time) tuples are collapsed so
    one image only shows up once per detected species.
    """
    simple_rows: List[dict] = []
    seen_keys = set()

    for rows in (combined_rows, animal_unclassified_rows, non_animal_rows):
        for row in rows:
            simple = _simplify_row(
                row, low_confidence_threshold=low_confidence_threshold
            )
            key = (
                simple["image_name"],
                simple["camera_location"],
                simple["species"],
                simple["date_time"],
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            simple_rows.append(simple)

    simple_rows.sort(
        key=lambda r: (
            r["camera_location"],
            r["date_time"],
            r["image_name"],
            r["species"],
        )
    )
    return simple_rows


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------

def _write_csv(path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _build_summary_rows(simple_rows: Iterable[Mapping[str, str]]) -> List[dict]:
    grouped: dict = defaultdict(
        lambda: {"total": 0, "animals": 0, "review": 0, "species": Counter()}
    )
    for row in simple_rows:
        camera = row.get("camera_location") or "Unknown"
        info = grouped[camera]
        info["total"] += 1
        if row.get("animal_detected") == "yes":
            info["animals"] += 1
        if row.get("review_needed") == "yes":
            info["review"] += 1
        species = row.get("species") or ""
        if species and species not in {"blank", ANIMAL_UNCLASSIFIED}:
            info["species"][species] += 1

    summary_rows = []
    for camera in sorted(grouped):
        info = grouped[camera]
        top = info["species"].most_common(1)
        summary_rows.append(
            {
                "camera_location": camera,
                "total_images": info["total"],
                "animals_detected": info["animals"],
                "review_needed": info["review"],
                "top_species": top[0][0] if top else "",
            }
        )
    return summary_rows


def write_simple_outputs(
    out_dir: Path,
    combined_rows: Iterable[Mapping[str, str]],
    animal_unclassified_rows: Iterable[Mapping[str, str]] = (),
    non_animal_rows: Iterable[Mapping[str, str]] = (),
    *,
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
) -> dict:
    """Write the four user-facing CSVs to ``out_dir`` and return a summary."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    simple_rows = build_simple_rows(
        combined_rows,
        animal_unclassified_rows,
        non_animal_rows,
        low_confidence_threshold=low_confidence_threshold,
    )

    final_path = out_dir / FINAL_RESULTS_CSV
    animal_path = out_dir / ANIMAL_RESULTS_CSV
    review_path = out_dir / REVIEW_NEEDED_CSV
    summary_path = out_dir / SUMMARY_BY_CAMERA_CSV

    animal_rows = [
        r
        for r in simple_rows
        if r.get("animal_detected") == "yes"
        and (r.get("species") or "").strip()
        and r.get("species") not in {"human", "vehicle", "blank"}
    ]
    review_rows = [r for r in simple_rows if r.get("review_needed") == "yes"]

    _write_csv(final_path, simple_rows, FINAL_RESULTS_COLUMNS)
    _write_csv(animal_path, animal_rows, FINAL_RESULTS_COLUMNS)
    _write_csv(review_path, review_rows, FINAL_RESULTS_COLUMNS)

    summary_rows = _build_summary_rows(simple_rows)
    _write_csv(summary_path, summary_rows, SUMMARY_COLUMNS)

    return {
        "final_results_path": str(final_path),
        "animal_results_path": str(animal_path),
        "review_needed_path": str(review_path),
        "summary_by_camera_path": str(summary_path),
        "final_results_rows": len(simple_rows),
        "animal_results_rows": len(animal_rows),
        "review_needed_rows": len(review_rows),
        "camera_count": len(summary_rows),
    }
