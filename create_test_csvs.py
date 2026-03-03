"""
Creates dummy CSV files in data/outputs/by_location/ for testing upload_to_drive.py
WITHOUT needing to run the full pipeline or ML models.
Run this once before testing upload_to_drive.py.
"""

import csv
from pathlib import Path

BY_LOCATION_DIR = Path("data/outputs/by_location")
BY_LOCATION_DIR.mkdir(parents=True, exist_ok=True)

FIELDNAMES = [
    "CameraName", "DeploymentFolder", "Image#", "Species",
    "# of Individuals", "Date", "Time", "has_animal",
    "model_certainty", "Notes"
]

# Fake data for each camera
CAMERAS = {
    "Research_Park": [
        {"CameraName": "Research_Park", "DeploymentFolder": "2024_01_15_ResPark", "Image#": "IMG_0001", "Species": "coyote", "# of Individuals": "1", "Date": "20240115", "Time": "06:32:11", "has_animal": "1", "model_certainty": "0.93", "Notes": ""},
        {"CameraName": "Research_Park", "DeploymentFolder": "2024_01_15_ResPark", "Image#": "IMG_0002", "Species": "rabbit", "# of Individuals": "2", "Date": "20240115", "Time": "07:10:05", "has_animal": "1", "model_certainty": "0.87", "Notes": ""},
        {"CameraName": "Research_Park", "DeploymentFolder": "2024_01_15_ResPark", "Image#": "IMG_0005", "Species": "human",  "# of Individuals": "1", "Date": "20240115", "Time": "08:45:00", "has_animal": "0", "model_certainty": "0.99", "Notes": "jogger"},
    ],
    "Bonita_Canyon1": [
        {"CameraName": "Bonita_Canyon1", "DeploymentFolder": "2024_02_01_BonitaCanyon1", "Image#": "IMG_0001", "Species": "deer",   "# of Individuals": "3", "Date": "20240201", "Time": "19:05:22", "has_animal": "1", "model_certainty": "0.91", "Notes": ""},
        {"CameraName": "Bonita_Canyon1", "DeploymentFolder": "2024_02_01_BonitaCanyon1", "Image#": "IMG_0003", "Species": "raccoon","# of Individuals": "1", "Date": "20240201", "Time": "21:30:44", "has_animal": "1", "model_certainty": "0.85", "Notes": ""},
    ],
    "Bonita_Canyon2": [
        {"CameraName": "Bonita_Canyon2", "DeploymentFolder": "2024_02_01_BonitaCanyon2", "Image#": "IMG_0001", "Species": "bobcat", "# of Individuals": "1", "Date": "20240202", "Time": "05:15:33", "has_animal": "1", "model_certainty": "0.78", "Notes": ""},
    ],
    "Marshtrail": [
        {"CameraName": "Marshtrail", "DeploymentFolder": "2024_03_10_Marshtrail", "Image#": "IMG_0001", "Species": "squirrel","# of Individuals": "1", "Date": "20240310", "Time": "10:22:01", "has_animal": "1", "model_certainty": "0.82", "Notes": ""},
        {"CameraName": "Marshtrail", "DeploymentFolder": "2024_03_10_Marshtrail", "Image#": "IMG_0002", "Species": "skunk",   "# of Individuals": "2", "Date": "20240310", "Time": "20:55:17", "has_animal": "1", "model_certainty": "0.90", "Notes": ""},
    ],
}

for camera_name, rows in CAMERAS.items():
    out_path = BY_LOCATION_DIR / f"{camera_name}_results.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"✓ Created {out_path} ({len(rows)} rows)")

print(f"\nAll dummy CSVs created in: {BY_LOCATION_DIR}")
print("Now update CAMERA_FOLDERS in upload_to_drive.py with YOUR personal Drive folder IDs, then run it.")