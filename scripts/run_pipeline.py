# runs the pipeline in the correct order:
# index > download > manifest > megadetector > speciesnet > inference > metadata > output
#
# IMPORTANT: Run this from your .venv so all steps use Python 3.11:
#   source .venv/bin/activate
#   python scripts/run_pipeline.py
#
# sys.executable ensures every subprocess uses the same Python that launched this script.

import subprocess
import sys
import shutil
import time
from pathlib import Path

PYTHON = sys.executable

STEPS = [
    ("Index Drive",          [PYTHON, "scripts/build_index.py"]),
    ("Download Images",      [PYTHON, "scripts/download_drive.py"]),
    ("Create Manifest",      [PYTHON, "scripts/make_manifest.py"]),
    ("Run MegaDetector",     [PYTHON, "scripts/run_megadetector.py"]),
    ("Run SpeciesNet",       [PYTHON, "scripts/run_speciesnet.py"]),
    ("Parse ML Results",     [PYTHON, "scripts/run_inference.py"]),
    ("Extract Metadata",     [PYTHON, "scripts/extract_metadata.py"]),
    ("Generate Output CSVs", [PYTHON, "scripts/make_output.py"]),
]

STAGING_DIR = Path("data/staging")


def main():
    # Verify we're running in the venv with Python 3.11
    print(f"Using Python: {PYTHON}")
    print(f"Python version: {sys.version}")

    if "3.13" in sys.version:
        print("\nWARNING: You're using Python 3.13 (system default).")
        print("MegaDetector and SpeciesNet require Python 3.11.")
        print("Activate your venv first:")
        print("  source .venv/bin/activate")
        print("  python scripts/run_pipeline.py")
        sys.exit(1)

    print("=" * 60)
    print("WILDLIFE CAMERA IMAGE PROCESSING PIPELINE")
    print("=" * 60)

    total_start = time.time()
    results = []

    for i, (name, cmd) in enumerate(STEPS, 1):
        print(f"\n[Step {i}/{len(STEPS)}] {name}")
        print("-" * 40)

        start = time.time()
        result = subprocess.run(cmd)
        duration = time.time() - start

        success = result.returncode == 0
        results.append((name, success, duration))

        if success:
            print(f"  [OK] {name} ({duration:.1f}s)")
        else:
            print(f"  [FAILED] {name} (exit code {result.returncode})")
            print(f"Stopped due to error on: {name}")
            break

    total_duration = time.time() - total_start

    # Summary
    print("\n" + "=" * 60)
    print("PIPELINE SUMMARY")
    print("=" * 60)

    for name, success, duration in results:
        status = "[OK]" if success else "[FAILED]"
        print(f"  {status} {name}: {duration:.1f}s")

    print(f"\nTotal time: {total_duration:.1f}s ({total_duration/60:.1f} min)")

    if not all(s for _, s, _ in results):
        sys.exit(1)

    print("\nPipeline complete!")
    print("\nOutputs:")
    print("  - Per-location CSVs: data/outputs/by_location/")
    print("  - MegaDetector results: data/outputs/md_results.json")
    print("  - SpeciesNet results: data/outputs/speciesnet_results.json")

    # Optional: clean up staging to free disk space
    if STAGING_DIR.exists():
        staging_size = sum(f.stat().st_size for f in STAGING_DIR.rglob("*") if f.is_file())
        staging_mb = staging_size / (1024 * 1024)
        if staging_mb > 1:
            print(f"\nStaging directory: {staging_mb:.0f} MB")
            response = input("Delete staging images to free disk space? [y/N]: ").strip().lower()
            if response == "y":
                shutil.rmtree(STAGING_DIR)
                STAGING_DIR.mkdir(parents=True, exist_ok=True)
                print(f"  Cleared {staging_mb:.0f} MB from {STAGING_DIR}")
            else:
                print("  Keeping staging images.")


if __name__ == "__main__":
    main()
