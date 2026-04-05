# scripts/ml/run_speciesnet.py
# Install: pip install speciesnet --use-pep517
# Docs: https://github.com/google/cameratrapai

import argparse
import json
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Optional


STAGING_DIR = Path("data/staging")
SPECIESNET_JSON = Path("data/outputs/speciesnet_results.json")

COUNTRY = "United States"
ADMIN1_REGION = "California"


def count_images(directory: Path) -> int:
    extensions = {".jpg", ".jpeg", ".png"}
    count = 0
    for f in directory.rglob("*"):
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in extensions:
            count += 1
    return count


def parse_prediction_label(prediction_str: str) -> str:
    if not prediction_str or not isinstance(prediction_str, str):
        return "unknown"

    parts = [p.strip() for p in prediction_str.split(";")]
    for value in reversed(parts):
        if value:
            return value.lower()

    return "unknown"


@contextmanager
def _track_speciesnet_batch_progress(
    *,
    progress_callback: Optional[Callable[[dict], None]],
    total_images: int,
) -> Iterator[None]:
    if not progress_callback or total_images <= 0:
        yield
        return

    try:
        from speciesnet.classifier import SpeciesNetClassifier
    except ImportError:
        yield
        return

    original_batch_predict = SpeciesNetClassifier.batch_predict
    processed_images = 0
    progress_lock = threading.Lock()

    def wrapped_batch_predict(self, filepaths, imgs):
        nonlocal processed_images
        predictions = original_batch_predict(self, filepaths, imgs)
        with progress_lock:
            processed_images = min(total_images, processed_images + len(filepaths))
            current_processed = processed_images
        try:
            progress_callback(
                {
                    "processed_images": current_processed,
                    "total_images": total_images,
                }
            )
        except Exception:
            pass
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
) -> dict:
    staging_dir = Path(staging_dir)
    out_json = Path(out_json)

    if not staging_dir.exists():
        raise FileNotFoundError(f"Staging directory not found: {staging_dir}")

    num_images = count_images(staging_dir)

    if num_images == 0:
        print("No images found in staging directory.")
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps({"predictions": []}), encoding="utf-8")
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

    with _track_speciesnet_batch_progress(
        progress_callback=progress_callback,
        total_images=num_images,
    ):
        predictions_dict = model.predict(
            instances_dict=instances_dict,
            run_mode=run_mode,
            batch_size=batch_size,
            progress_bars=progress_bars,
            predictions_json=str(out_json),
        )

    if predictions_dict is not None and not out_json.exists():
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(predictions_dict, f, ensure_ascii=False, indent=2)

    species_counts = {}
    classified_images = 0

    if out_json.exists():
        with open(out_json, "r", encoding="utf-8") as f:
            results = json.load(f)

        predictions = results.get("predictions", [])
        classified_images = len(predictions)

        for pred in predictions:
            prediction_str = pred.get("prediction", "")
            label = parse_prediction_label(prediction_str)
            species_counts[label] = species_counts.get(label, 0) + 1

        print(f"\n✓ SpeciesNet complete")
        print(f"  Classified: {classified_images} images")
        print(f"\n  Species found:")
        for species, count in sorted(species_counts.items(), key=lambda x: (-x[1], x[0])):
            print(f"    {species}: {count}")

    return {
        "speciesnet_json": str(out_json),
        "classified_images": classified_images,
        "species_counts": species_counts,
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
        staging_dir=Path(args.staging_dir),
        out_json=Path(args.out_json),
        country=args.country,
        admin1_region=args.admin1_region,
        batch_size=args.batch_size,
        run_mode=args.run_mode,
        progress_bars=not args.no_progress_bars,
        geofence=not args.no_geofence,
    )


if __name__ == "__main__":
    main()