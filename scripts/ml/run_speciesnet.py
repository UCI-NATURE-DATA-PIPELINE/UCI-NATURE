# scripts/ml/run_speciesnet.py
# Install: pip install speciesnet --use-pep517
# Docs: https://github.com/google/cameratrapai

import argparse
import json
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ml.speciesnet_parsing import resolve_prediction, safe_float


STAGING_DIR = Path("data/staging")
SPECIESNET_JSON = Path("data/outputs/speciesnet_results.json")

COUNTRY = "United States"
ADMIN1_REGION = "California"


def _resolve_repo_path(path_value) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def count_images(directory: Path) -> int:
    extensions = {".jpg", ".jpeg", ".png"}
    count = 0
    for f in directory.rglob("*"):
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in extensions:
            count += 1
    return count


ANIMAL_CATEGORY = {"1", "animal"}
PERSON_CATEGORY = {"2", "human"}
DETECTION_THRESHOLD = 0.5
PROGRESS_HEARTBEAT_SECONDS = 10


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


def _emit_speciesnet_progress(
    progress_callback: Optional[Callable[[dict], None]],
    *,
    processed_images: int,
    total_images: int,
    status_text: str,
) -> None:
    percentage = round((processed_images / total_images) * 100) if total_images else 0
    payload = {
        "stage_name": "Run SpeciesNet",
        "processed_images": processed_images,
        "total_images": total_images,
        "percentage": percentage,
        "status_text": status_text,
    }
    if not progress_callback:
        return
    try:
        progress_callback(payload)
    except Exception:
        pass


@contextmanager
def _track_speciesnet_batch_progress(
    *,
    progress_callback: Optional[Callable[[dict], None]],
    total_images: int,
    progress_state: dict[str, int],
) -> Iterator[None]:
    if total_images <= 0:
        yield
        return

    try:
        from speciesnet.classifier import SpeciesNetClassifier
    except ImportError:
        yield
        return

    original_batch_predict = SpeciesNetClassifier.batch_predict
    progress_lock = threading.Lock()

    def wrapped_batch_predict(self, filepaths, imgs):
        predictions = original_batch_predict(self, filepaths, imgs)
        with progress_lock:
            progress_state["processed_images"] = min(
                total_images,
                progress_state["processed_images"] + len(filepaths),
            )
            current_processed = progress_state["processed_images"]
        _emit_speciesnet_progress(
            progress_callback,
            processed_images=current_processed,
            total_images=total_images,
            status_text=(
                f"SpeciesNet processed {current_processed} of {total_images} image(s)"
            ),
        )
        return predictions

    SpeciesNetClassifier.batch_predict = wrapped_batch_predict
    try:
        yield
    finally:
        SpeciesNetClassifier.batch_predict = original_batch_predict


def run_speciesnet_model(
    staging_dir: Path = STAGING_DIR,
    out_json: Path = SPECIESNET_JSON,
    country: str = COUNTRY,
    admin1_region: str = ADMIN1_REGION,
    batch_size: int = 8,
    run_mode: str = "multi_thread",
    progress_bars: bool = True,
    geofence: bool = True,
    progress_callback: Optional[Callable[[dict], None]] = None,
    filepaths: Optional[list[str]] = None,
) -> dict:
    staging_dir = Path(staging_dir)
    out_json = Path(out_json)

    if not staging_dir.exists():
        raise FileNotFoundError(f"Staging directory not found: {staging_dir}")

    if filepaths is not None:
        num_images = len(filepaths)
        print(f"Using explicit filepath list: {num_images} images")
    else:
        num_images = count_images(staging_dir)

    if num_images == 0:
        print("No images found in staging directory.")
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps({"predictions": []}), encoding="utf-8")
        _emit_speciesnet_progress(
            progress_callback,
            processed_images=0,
            total_images=0,
            status_text="No images found for SpeciesNet",
        )
        return {
            "speciesnet_json": str(out_json),
            "classified_images": 0,
            "species_counts": {},
            "used_cli_adapter": False,
        }

    print(f"Found {num_images} images to classify")
    print(f"Geofencing: {country} / {admin1_region}")
    print("This may take a while depending on your hardware...")

    out_json.parent.mkdir(parents=True, exist_ok=True)
    if out_json.exists():
        out_json.unlink()
        print(f"Removed stale SpeciesNet predictions file: {out_json}")

    try:
        from speciesnet import DEFAULT_MODEL, SpeciesNet
        from speciesnet.utils import prepare_instances_dict
    except ImportError as exc:
        raise RuntimeError(
            "SpeciesNet is not installed in the current Python environment. "
            "Install the 'speciesnet' package to run the pipeline."
        ) from exc

    if filepaths is not None:
        instances_dict = prepare_instances_dict(
            filepaths=filepaths,
            country=country,
            admin1_region=admin1_region,
        )
    else:
        instances_dict = prepare_instances_dict(
            folders=[str(staging_dir)],
            country=country,
            admin1_region=admin1_region,
        )

    model = SpeciesNet(
        DEFAULT_MODEL,
        components="all",
        geofence=geofence,
        multiprocessing=(run_mode == "multi_process"),
    )

    progress_state = {"processed_images": 0}
    stop_event = threading.Event()

    def emit_heartbeat() -> None:
        while not stop_event.wait(PROGRESS_HEARTBEAT_SECONDS):
            current_processed = progress_state["processed_images"]
            _emit_speciesnet_progress(
                progress_callback,
                processed_images=current_processed,
                total_images=num_images,
                status_text=(
                    "SpeciesNet still running "
                    f"({current_processed}/{num_images} image(s) processed)"
                ),
            )

    _emit_speciesnet_progress(
        progress_callback,
        processed_images=0,
        total_images=num_images,
        status_text="Initializing SpeciesNet",
    )
    heartbeat_thread = threading.Thread(target=emit_heartbeat, daemon=True)
    heartbeat_thread.start()

    with _track_speciesnet_batch_progress(
        progress_callback=progress_callback,
        total_images=num_images,
        progress_state=progress_state,
    ):
        try:
            predictions_dict = model.predict(
                instances_dict=instances_dict,
                run_mode=run_mode,
                batch_size=batch_size,
                progress_bars=progress_bars,
                predictions_json=str(out_json),
            )
        finally:
            stop_event.set()
            heartbeat_thread.join(timeout=1)

    _emit_speciesnet_progress(
        progress_callback,
        processed_images=num_images,
        total_images=num_images,
        status_text="SpeciesNet inference complete",
    )

    if predictions_dict is not None and not out_json.exists():
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(predictions_dict, f, ensure_ascii=False, indent=2)

    species_counts = {}
    classified_images = 0
    resolved_species_rows = 0
    unresolved_animal_rows = 0

    if out_json.exists():
        with open(out_json, "r", encoding="utf-8") as f:
            results = json.load(f)

        predictions = results.get("predictions", [])
        classified_images = len(predictions)

        for pred in predictions:
            detections = pred.get("detections") or []
            has_animal = _count_detections(detections, ANIMAL_CATEGORY, DETECTION_THRESHOLD) > 0
            has_human = _count_detections(detections, PERSON_CATEGORY, DETECTION_THRESHOLD) > 0
            resolved = resolve_prediction(
                pred,
                has_animal=has_animal,
                has_human=has_human,
            )
            label = resolved.get("resolved_label", "") or "unknown"
            species_counts[label] = species_counts.get(label, 0) + 1
            if has_animal:
                if int(resolved.get("resolved_species_level", 0)):
                    resolved_species_rows += 1
                else:
                    unresolved_animal_rows += 1

        print(f"\n✓ SpeciesNet complete")
        print(f"  Classified: {classified_images} images")
        print(f"  Resolved species: {resolved_species_rows}")
        print(f"  Unresolved animal / taxon rows: {unresolved_animal_rows}")
        print(f"\n  Species found:")
        for species, count in sorted(species_counts.items(), key=lambda x: (-x[1], x[0])):
            print(f"    {species}: {count}")

    return {
        "speciesnet_json": str(out_json),
        "classified_images": classified_images,
        "species_counts": species_counts,
        "resolved_species_rows": resolved_species_rows,
        "unresolved_animal_rows": unresolved_animal_rows,
        "batch_size": batch_size,
        "used_cli_adapter": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Run SpeciesNet on staged images.")
    parser.add_argument("--staging_dir", default=str(STAGING_DIR))
    parser.add_argument("--out_json", default=str(SPECIESNET_JSON))
    parser.add_argument("--country", default=COUNTRY)
    parser.add_argument("--admin1_region", default=ADMIN1_REGION)
    parser.add_argument("--batch_size", type=int, default=8)
    parser.add_argument(
        "--run_mode",
        default="multi_thread",
        choices=["single_thread", "multi_thread", "multi_process"],
    )
    parser.add_argument("--no_progress_bars", action="store_true")
    parser.add_argument("--no_geofence", action="store_true")
    args = parser.parse_args()

    run_speciesnet_model(
        staging_dir=_resolve_repo_path(args.staging_dir),
        out_json=_resolve_repo_path(args.out_json),
        country=args.country,
        admin1_region=args.admin1_region,
        batch_size=args.batch_size,
        run_mode=args.run_mode,
        progress_bars=not args.no_progress_bars,
        geofence=not args.no_geofence,
    )


if __name__ == "__main__":
    main()
