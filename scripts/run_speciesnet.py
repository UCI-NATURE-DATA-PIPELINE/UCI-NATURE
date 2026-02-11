# Runs SpeciesNet on downloaded images for species classification.
# Install: pip install speciesnet --use-pep517
# Docs: https://github.com/google/cameratrapai

import subprocess
import sys
import json
from pathlib import Path

# Paths
STAGING_DIR = Path("data/staging")
SPECIESNET_JSON = Path("data/outputs/speciesnet_results.json")

# Geofencing: UCI is in California, USA
COUNTRY = "USA"
ADMIN1_REGION = "CA"


def count_images(directory: Path) -> int:
    extensions = {".jpg", ".jpeg", ".png"}
    count = 0
    for f in directory.iterdir():
        if f.is_file() and f.suffix.lower() in extensions:
            count += 1
    return count


def parse_prediction_label(prediction_str: str) -> str:
    """
    Parse SpeciesNet prediction string into a readable label.
    Format: "uuid;class;order;family;genus;species;common_name"
    Example: "e4d1e892-...;mammalia;rodentia;sciuridae;;;sciuridae family"
    Returns the common name (last field), or the most specific taxonomy available.
    """
    if not prediction_str:
        return "unknown"
    parts = prediction_str.split(";")
    # Last field is common name
    if len(parts) >= 7 and parts[6].strip():
        return parts[6].strip()
    # Fall back to most specific non-empty taxonomy field
    for i in range(6, 0, -1):
        if i < len(parts) and parts[i].strip():
            return parts[i].strip()
    return "unknown"


def main():
    if not STAGING_DIR.exists():
        raise FileNotFoundError(f"Staging directory not found: {STAGING_DIR}")

    num_images = count_images(STAGING_DIR)

    if num_images == 0:
        print("No images found in staging directory.")
        SPECIESNET_JSON.parent.mkdir(parents=True, exist_ok=True)
        SPECIESNET_JSON.write_text(json.dumps({"predictions": []}))
        return

    print(f"Found {num_images} images to classify")
    print(f"Geofencing: {COUNTRY} / {ADMIN1_REGION}")
    print("This may take a while depending on your hardware...")

    SPECIESNET_JSON.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m",
        "speciesnet.scripts.run_model",
        "--folders", str(STAGING_DIR),
        "--predictions_json", str(SPECIESNET_JSON),
        "--country", COUNTRY,
        "--admin1_region", ADMIN1_REGION,
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"\n❌ SpeciesNet failed with exit code {result.returncode}")
        print("Troubleshooting:")
        print("  1. Make sure you're in the .venv: source .venv/bin/activate")
        print("  2. Check speciesnet is installed: pip show speciesnet")
        print("  3. Try: pip install speciesnet --use-pep517")
        sys.exit(result.returncode)

    # Print summary
    if SPECIESNET_JSON.exists():
        with open(SPECIESNET_JSON, "r") as f:
            results = json.load(f)

        predictions = results.get("predictions", [])
        species_counts = {}
        for pred in predictions:
            prediction_str = pred.get("prediction", "")
            label = parse_prediction_label(prediction_str)
            species_counts[label] = species_counts.get(label, 0) + 1

        print(f"\n✓ SpeciesNet complete")
        print(f"  Classified: {len(predictions)} images")
        print(f"\n  Species found:")
        for species, count in sorted(species_counts.items(), key=lambda x: -x[1]):
            print(f"    {species}: {count}")


if __name__ == "__main__":
    main()