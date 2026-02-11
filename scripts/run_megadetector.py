# Runs MegaDetector on downloaded images and outputs md_results.json
# This script is called by run_pipeline.py after download_drive.py
#
# Uses subprocess to call MegaDetector as a module (python -m megadetector...)
# because direct imports (from megadetector.detection...) don't resolve correctly
# in all environments.

import subprocess
import sys
import json
from pathlib import Path

# Paths
STAGING_DIR = Path("data/staging")
MD_RESULTS_JSON = Path("data/outputs/md_results.json")

# MegaDetector model to use
# Options: "MDV5A", "MDV5B", or path to a downloaded .pt file
MODEL_NAME = "MDV5A"


def count_images(directory: Path) -> int:
    """Count image files in staging directory."""
    extensions = {".jpg", ".jpeg", ".png"}
    count = 0
    for f in directory.iterdir():
        if f.is_file() and f.suffix.lower() in extensions:
            count += 1
    return count


def main():
    """
    Run MegaDetector on all images in staging directory.
    """
    
    if not STAGING_DIR.exists():
        raise FileNotFoundError(
            f"Staging directory not found: {STAGING_DIR}\n"
            "Run download_drive.py first."
        )
    
    num_images = count_images(STAGING_DIR)
    
    if num_images == 0:
        print("No images found in staging directory.")
        # Create empty results so downstream scripts don't fail
        MD_RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
        MD_RESULTS_JSON.write_text(json.dumps({"images": [], "detection_categories": {}}))
        return
    
    print(f"Found {num_images} images to process")
    print(f"Using model: {MODEL_NAME}")
    print("This may take a while depending on your hardware...")
    
    # Create output directory
    MD_RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    
    # Run MegaDetector as a module via subprocess
    # This is the same command that works manually in the terminal:
    #   python3 -m megadetector.detection.run_detector_batch MDV5A data/staging data/outputs/md_results.json --recursive --quiet
    cmd = [
        sys.executable, "-m",
        "megadetector.detection.run_detector_batch",
        MODEL_NAME,
        str(STAGING_DIR),
        str(MD_RESULTS_JSON),
        "--recursive",
        "--quiet",
    ]
    
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    
    if result.returncode != 0:
        print(f"\n❌ MegaDetector failed with exit code {result.returncode}")
        print("Troubleshooting:")
        print("  1. Make sure you're in the .venv: source .venv/bin/activate")
        print("  2. Check megadetector is installed: pip show megadetector")
        print("  3. Check numpy version: pip show numpy (must be <2.0)")
        sys.exit(result.returncode)
    
    # Print summary from results
    if MD_RESULTS_JSON.exists():
        with open(MD_RESULTS_JSON, "r") as f:
            results = json.load(f)
        
        total = len(results.get("images", []))
        detections = sum(
            1 for img in results.get("images", [])
            if img.get("detections") and len(img["detections"]) > 0
        )
        
        print(f"\n✓ MegaDetector complete")
        print(f"  Processed: {total} images")
        print(f"  With detections: {detections}")
        print(f"  Empty/blank: {total - detections}")
        print(f"  Results: {MD_RESULTS_JSON}")


if __name__ == "__main__":
    main()