"""
Split output.csv by camera location for Drive upload.
Creates one CSV per camera: Research Park, Bonita Canyon1, Bonita Canyon2, Marshtrail
"""

import csv
from pathlib import Path
from collections import defaultdict

# Input
OUTPUT_CSV = Path("data/outputs/output.csv")
METADATA_CSV = Path("data/outputs/metadata.csv")

# Output directory
BY_LOCATION_DIR = Path("data/outputs/by_location")

# Camera name mapping (normalize variations)
CAMERA_MAPPING = {
    "research park": "Research_Park",
    "respark": "Research_Park",
    "bonita canyon1": "Bonita_Canyon1",
    "bonita canyon2": "Bonita_Canyon2", 
    "marshtrail": "Marshtrail",
    "marsh trail": "Marshtrail",
}


def extract_camera_from_path(local_path: str) -> str:
    """
    Extract camera name from local_path.
    Example: "data/staging/Research Park/IMG001.jpg" -> "Research_Park"
    """
    if not local_path:
        return "Unknown"
    
    parts = Path(local_path).parts
    
    # Look for camera folder (usually after "staging")
    try:
        staging_idx = parts.index("staging")
        if staging_idx + 1 < len(parts):
            camera = parts[staging_idx + 1]
            
            # Normalize camera name
            camera_lower = camera.lower().replace("_", " ")
            return CAMERA_MAPPING.get(camera_lower, camera.replace(" ", "_"))
    except ValueError:
        pass
    
    # Fallback: check each part
    for part in parts:
        part_lower = part.lower().replace("_", " ")
        if part_lower in CAMERA_MAPPING:
            return CAMERA_MAPPING[part_lower]
    
    return "Unknown"


def load_ml_data(metadata_csv: Path) -> dict:
    """Load ML outputs from metadata.csv indexed by file_id"""
    ml_by_id = {}
    
    if not metadata_csv.exists():
        return ml_by_id
    
    with open(metadata_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            file_id = row.get("file_id", "")
            if file_id:
                ml_by_id[file_id] = {
                    "has_animal": row.get("has_animal", ""),
                    "has_human": row.get("has_human", ""),
                    "species": row.get("species", ""),
                    "count": row.get("count", ""),
                    "model_certainty": row.get("model_certainty", ""),
                    "date": row.get("date", ""),
                    "time": row.get("time", ""),
                }
    
    return ml_by_id


def main():
    # Load ML data
    ml_data = load_ml_data(METADATA_CSV)
    
    # Group rows by camera
    by_camera = defaultdict(list)
    
    if OUTPUT_CSV.exists():
        with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                file_id = row.get("file_id", "")
                local_path = row.get("local_path", "")
                
                camera = extract_camera_from_path(local_path)
                
                # Get ML data for this image
                ml = ml_data.get(file_id, {})
                
                # Build Julie's CSV format
                julie_row = {
                    "CameraName": camera,
                    "DeploymentFolder": "",  # To be filled by Julie
                    "Image#": row.get("file_name", ""),
                    "Species": ml.get("species", ""),
                    "# of Individuals": ml.get("count", ""),
                    "Date": ml.get("date", ""),
                    "Time": ml.get("time", ""),
                    "has_animal": ml.get("has_animal", ""),
                    "model_certainty": ml.get("model_certainty", ""),
                    "Notes": "",
                }
                
                by_camera[camera].append(julie_row)
    else:
        # Fallback: convert existing per-camera CSVs (e.g., ResPark.csv) into *_results.csv files
        if not BY_LOCATION_DIR.exists():
            raise FileNotFoundError(f"{OUTPUT_CSV} not found. Run make_output.py first.")
        
        input_csvs = sorted(BY_LOCATION_DIR.glob("*.csv"))
        if not input_csvs:
            raise FileNotFoundError(f"{OUTPUT_CSV} not found. Run make_output.py first.")
        
        for csv_path in input_csvs:
            if csv_path.name.endswith("_results.csv"):
                continue
            
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                src_fields = reader.fieldnames or []
                
                base_name = csv_path.stem
                base_lower = base_name.lower().replace("_", " ").replace("-", " ")
                camera = CAMERA_MAPPING.get(base_lower, base_name.replace(" ", "_"))
                
                for row in reader:
                    # Normalize/translate from existing format to the uploader's expected format
                    julie_row = {
                        "CameraName": row.get("CameraName", camera) or camera,
                        "DeploymentFolder": row.get("DeploymentFolder", "") or "",
                        "Image#": row.get("Image#", "") or row.get("Image", "") or row.get("file_name", "") or "",
                        "Species": row.get("Species", "") or row.get("species", "") or "",
                        "# of Individuals": row.get("# of Individuals", "") or row.get("count", "") or "",
                        "Date": row.get("Date", "") or row.get("date", "") or "",
                        "Time": row.get("Time", "") or row.get("time", "") or "",
                        "has_animal": row.get("has_animal", "") or row.get("HasAnimal", "") or "",
                        "model_certainty": row.get("model_certainty", "") or row.get("ModelCertainty", "") or "",
                        "Notes": row.get("Notes", "") or "",
                    }
                    by_camera[camera].append(julie_row)
    
    # Write CSV for each camera
    BY_LOCATION_DIR.mkdir(parents=True, exist_ok=True)
    
    fieldnames = [
        "CameraName", "DeploymentFolder", "Image#", "Species",
        "# of Individuals", "Date", "Time", "has_animal",
        "model_certainty", "Notes"
    ]
    
    for camera, rows in by_camera.items():
        output_file = BY_LOCATION_DIR / f"{camera}_results.csv"
        
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"✓ {camera}: {len(rows)} rows -> {output_file}")
    
    print(f"\nTotal cameras: {len(by_camera)}")
    print(f"Output directory: {BY_LOCATION_DIR}")


if __name__ == "__main__":
    main()