from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path


REVIEW_DECISIONS_CSV = Path("data/outputs/review_decisions.csv")
REVIEW_DECISION_FIELDS = [
    "filepath",
    "review_status",
    "reviewed_species",
    "review_reason",
    "updated_at",
]


def normalize_review_path(filepath: str) -> str:
    path_value = (filepath or "").strip().replace("\\", "/")
    while "//" in path_value:
        path_value = path_value.replace("//", "/")
    if path_value.startswith("./"):
        path_value = path_value[2:]
    marker = "data/staging/"
    idx = path_value.find(marker)
    if idx >= 0:
        path_value = path_value[idx:]
    return path_value


def normalize_review_status(status: str) -> str:
    value = (status or "pending").strip().lower()
    if value not in {"pending", "confirmed", "flagged"}:
        return "pending"
    return value


def normalize_review_species(species: str) -> str:
    value = (species or "").strip().lower().replace("_", " ")
    while "  " in value:
        value = value.replace("  ", " ")
    return value.replace(" ", "_") if value == "animal unclassified" else value


def load_review_decisions(path: Path = REVIEW_DECISIONS_CSV) -> dict[str, dict[str, str]]:
    path = Path(path)
    if not path.exists():
        return {}

    decisions: dict[str, dict[str, str]] = {}
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            filepath = normalize_review_path(row.get("filepath", ""))
            if not filepath:
                continue
            decisions[filepath] = {
                "filepath": filepath,
                "review_status": normalize_review_status(row.get("review_status", "")),
                "reviewed_species": normalize_review_species(row.get("reviewed_species", "")),
                "review_reason": (row.get("review_reason") or "").strip(),
                "updated_at": (row.get("updated_at") or "").strip(),
            }

    return decisions


def write_review_decisions(
    decisions: dict[str, dict[str, str]],
    path: Path = REVIEW_DECISIONS_CSV,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(
        decisions.values(),
        key=lambda row: (
            row.get("filepath", ""),
            row.get("updated_at", ""),
        ),
    )
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_DECISION_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in REVIEW_DECISION_FIELDS})


def upsert_review_decision(
    *,
    filepath: str,
    review_status: str,
    reviewed_species: str = "",
    review_reason: str = "",
    path: Path = REVIEW_DECISIONS_CSV,
) -> dict[str, str]:
    normalized_path = normalize_review_path(filepath)
    if not normalized_path:
        raise ValueError("filepath is required")

    decisions = load_review_decisions(path)
    decisions[normalized_path] = {
        "filepath": normalized_path,
        "review_status": normalize_review_status(review_status),
        "reviewed_species": normalize_review_species(reviewed_species),
        "review_reason": (review_reason or "").strip(),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    write_review_decisions(decisions, path)
    return decisions[normalized_path]
