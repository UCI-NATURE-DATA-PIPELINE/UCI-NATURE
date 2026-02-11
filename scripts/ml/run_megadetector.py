import json
from pathlib import Path
from megadetector.utils import path_utils
from megadetector.detection.run_detector_batch import load_and_run_detector_batch

def main():
    image_folder = Path("data/staging")
    output_file = Path("data/outputs/md_results.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    image_files = path_utils.find_images(str(image_folder), recursive=True)
    print("Found", len(image_files), "images")

    detector = "MDV5A"
    results = load_and_run_detector_batch(detector, image_files, quiet=True)


    if isinstance(results, list):
        results = {
            "info": {"generated_by": "scripts/ml/run_megadetector.py"},
            "detection_categories": {"1": "animal", "2": "person", "3": "vehicle"},
            "images": results,
        }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f)

    print("Wrote:", output_file, "bytes:", output_file.stat().st_size)

if __name__ == "__main__":
    main()