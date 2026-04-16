from __future__ import annotations

import json
from typing import Any


ANIMAL_UNCLASSIFIED = "animal_unclassified"

BLANK_LABELS = {"blank", "no cv result"}
HUMAN_LABELS = {"human", "homo sapiens", "person"}
VEHICLE_LABELS = {"vehicle", "car", "bike"}
NON_ANIMAL_LABELS = BLANK_LABELS | HUMAN_LABELS | VEHICLE_LABELS

NON_SPECIES_COMMON_LABELS = {
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

LABEL_ALIASES = {
    "canis latrans": "coyote",
    "urocyon cinereoargenteus": "fox",
    "grey fox": "fox",
    "gray fox": "fox",
    "vulpes vulpes": "fox",
    "red fox": "fox",
    "felis catus": "cat",
    "domestic cat": "cat",
    "canis lupus familiaris": "dog",
    "domestic dog": "dog",
    "procyon lotor": "raccoon",
    "didelphis virginiana": "opossum",
    "virginia opossum": "opossum",
    "mephitis mephitis": "skunk",
    "striped skunk": "skunk",
    "lynx rufus": "bobcat",
    "odocoileus hemionus": "deer",
    "mule deer": "deer",
    "odocoileus virginianus": "deer",
    "white-tailed deer": "deer",
    "cervidae family": "deer",
    "sylvilagus bachmani": "rabbit",
    "brush rabbit": "rabbit",
    "sylvilagus audubonii": "rabbit",
    "desert cottontail": "rabbit",
    "otospermophilus beecheyi": "squirrel",
    "california ground squirrel": "squirrel",
    "sciurus niger": "squirrel",
    "eastern fox squirrel": "squirrel",
    "sciurus carolinensis": "squirrel",
    "eastern gray squirrel": "squirrel",
    "peromyscus species": "mouse",
    "muridae family": "mouse",
    "cricetidae family": "mouse",
    "rodentia": "rodent",
    "canidae family": "canine",
    "homo sapiens": "human",
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def normalize_label(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return LABEL_ALIASES.get(text, text)


def split_taxonomy_label(raw_label: str) -> dict[str, str]:
    parts = [part.strip() for part in str(raw_label or "").split(";")]
    while len(parts) < 7:
        parts.append("")

    return {
        "uuid": parts[0],
        "class": normalize_label(parts[1]),
        "order": normalize_label(parts[2]),
        "family": normalize_label(parts[3]),
        "genus": normalize_label(parts[4]),
        "species": normalize_label(parts[5]),
        "common": normalize_label(parts[6]),
    }


def label_from_taxonomy(raw_label: str) -> tuple[str, str]:
    if not raw_label:
        return "", ""

    parts = split_taxonomy_label(raw_label)
    common_name = parts["common"]
    genus = parts["genus"]
    species = parts["species"]
    family = parts["family"]
    order = parts["order"]
    class_name = parts["class"]

    if common_name:
        return common_name, "common"

    if genus and species and species != "species":
        if species.startswith(f"{genus} "):
            return normalize_label(species), "species_binomial"
        return normalize_label(f"{genus} {species}"), "species_binomial"

    if genus:
        return genus, "genus"
    if family:
        return family, "family"
    if order:
        return order, "order"
    if class_name:
        return class_name, "class"

    return normalize_label(raw_label), "label"


def is_species_level(label: str, rank: str) -> bool:
    normalized = normalize_label(label)
    if not normalized or normalized in NON_ANIMAL_LABELS or normalized == ANIMAL_UNCLASSIFIED:
        return False
    if rank == "species_binomial":
        return True
    if rank == "common":
        return normalized not in NON_SPECIES_COMMON_LABELS
    return False


def is_usable_taxon(label: str) -> bool:
    normalized = normalize_label(label)
    return bool(normalized) and normalized not in (BLANK_LABELS | HUMAN_LABELS | VEHICLE_LABELS | {"animal", "unknown"})


def parse_prediction_label(raw_label: str) -> dict[str, Any]:
    label, rank = label_from_taxonomy(raw_label)
    return {
        "label": label,
        "rank": rank,
        "raw_label": raw_label or "",
        "species_level": is_species_level(label, rank),
        "usable_taxon": is_usable_taxon(label),
    }


def extract_classification_candidates(prediction: dict, limit: int | None = None) -> list[dict[str, Any]]:
    classifications = prediction.get("classifications") or {}
    classes = classifications.get("classes") or []
    scores = classifications.get("scores") or []
    candidates: list[dict[str, Any]] = []

    for index, raw_label in enumerate(classes):
        score = safe_float(scores[index] if index < len(scores) else 0.0, 0.0)
        parsed = parse_prediction_label(raw_label)
        candidates.append(
            {
                "rank_index": index,
                "label": parsed["label"],
                "rank": parsed["rank"],
                "raw_label": parsed["raw_label"],
                "score": score,
                "species_level": bool(parsed["species_level"]),
                "usable_taxon": bool(parsed["usable_taxon"]),
            }
        )

    candidates.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    if limit is not None:
        return candidates[:limit]
    return candidates


def dump_candidate_labels_json(candidates: list[dict[str, Any]], limit: int = 5) -> str:
    trimmed = []
    for item in candidates[: max(0, int(limit))]:
        trimmed.append(
            {
                "label": item.get("label", ""),
                "rank": item.get("rank", ""),
                "raw_label": item.get("raw_label", ""),
                "score": round(safe_float(item.get("score", 0.0), 0.0), 6),
                "species_level": int(bool(item.get("species_level"))),
            }
        )
    return json.dumps(trimmed, ensure_ascii=False)


def resolve_prediction(
    prediction: dict,
    *,
    has_animal: bool,
    has_human: bool,
    species_score_floor: float = 0.20,
) -> dict[str, Any]:
    raw_prediction = parse_prediction_label(prediction.get("prediction", ""))
    raw_prediction_score = safe_float(
        prediction.get("prediction_score", prediction.get("score", 0.0)),
        0.0,
    )
    prediction_source = normalize_label(prediction.get("prediction_source", ""))

    candidates = extract_classification_candidates(prediction)
    top_species = next(
        (
            candidate
            for candidate in candidates
            if candidate.get("species_level")
            and candidate.get("label") not in NON_ANIMAL_LABELS
        ),
        None,
    )
    top_taxon = next(
        (
            candidate
            for candidate in candidates
            if candidate.get("usable_taxon")
            and candidate.get("label") not in NON_ANIMAL_LABELS
        ),
        None,
    )

    chosen = {
        "label": "",
        "rank": "",
        "raw_label": "",
        "score": 0.0,
        "species_level": False,
        "source": "",
    }

    if has_animal:
        if (
            raw_prediction.get("species_level")
            and raw_prediction.get("label") not in NON_ANIMAL_LABELS
        ):
            chosen = {
                "label": raw_prediction["label"],
                "rank": raw_prediction["rank"],
                "raw_label": raw_prediction["raw_label"],
                "score": raw_prediction_score,
                "species_level": True,
                "source": f"prediction:{prediction_source or 'classifier'}",
            }
        elif top_species and safe_float(top_species.get("score", 0.0), 0.0) >= species_score_floor:
            chosen = {
                "label": top_species["label"],
                "rank": top_species["rank"],
                "raw_label": top_species["raw_label"],
                "score": safe_float(top_species.get("score", 0.0), 0.0),
                "species_level": True,
                "source": f"classifications[{top_species['rank_index']}]:{prediction_source or 'classifier'}",
            }
        elif raw_prediction.get("usable_taxon"):
            chosen = {
                "label": raw_prediction["label"],
                "rank": raw_prediction["rank"],
                "raw_label": raw_prediction["raw_label"],
                "score": raw_prediction_score,
                "species_level": bool(raw_prediction.get("species_level")),
                "source": f"prediction:{prediction_source or 'classifier'}",
            }
        elif top_taxon:
            chosen = {
                "label": top_taxon["label"],
                "rank": top_taxon["rank"],
                "raw_label": top_taxon["raw_label"],
                "score": safe_float(top_taxon.get("score", 0.0), 0.0),
                "species_level": bool(top_taxon.get("species_level")),
                "source": f"classifications[{top_taxon['rank_index']}]:{prediction_source or 'classifier'}",
            }
        else:
            chosen = {
                "label": ANIMAL_UNCLASSIFIED,
                "rank": "fallback",
                "raw_label": raw_prediction.get("label") or "",
                "score": raw_prediction_score,
                "species_level": False,
                "source": f"fallback:{prediction_source or 'classifier'}",
            }
    elif has_human:
        chosen = {
            "label": "human",
            "rank": "common",
            "raw_label": raw_prediction.get("raw_label", ""),
            "score": raw_prediction_score,
            "species_level": False,
            "source": f"prediction:{prediction_source or 'detector'}",
        }
    else:
        chosen = {
            "label": "blank",
            "rank": "common",
            "raw_label": raw_prediction.get("raw_label", ""),
            "score": raw_prediction_score,
            "species_level": False,
            "source": f"prediction:{prediction_source or 'classifier'}",
        }

    return {
        "raw_prediction_label": raw_prediction.get("label", ""),
        "raw_prediction_rank": raw_prediction.get("rank", ""),
        "raw_prediction_score": raw_prediction_score,
        "prediction_source": prediction_source,
        "resolved_label": normalize_label(chosen.get("label", "")),
        "resolved_rank": chosen.get("rank", ""),
        "resolved_label_raw": chosen.get("raw_label", ""),
        "resolved_score": safe_float(chosen.get("score", 0.0), 0.0),
        "resolved_species_level": int(bool(chosen.get("species_level"))),
        "resolved_source": chosen.get("source", ""),
        "classification_candidates": candidates,
        "classification_candidates_json": dump_candidate_labels_json(candidates),
    }