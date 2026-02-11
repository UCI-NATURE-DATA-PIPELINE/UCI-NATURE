# Validates the final pipeline output
# Fixed: Unicode encoding issue on Windows

import csv
import sys
from pathlib import Path
from collections import Counter

OUTPUT_CSV = Path("data/outputs/output.csv")
MANIFEST = Path("data/outputs/manifest.csv")

REQUIRED_COLUMNS = [
    "image_id",
    "camera_name",
    "date",
    "time",
    "has_animal",
    "is_blank",
    "species",
    "count",
    "model_certainty",
]


def validate_columns(actual: list) -> tuple:
    missing = [c for c in REQUIRED_COLUMNS if c not in actual]
    extra = [c for c in actual if c not in REQUIRED_COLUMNS]
    return len(missing) == 0, missing, extra


def validate_rows(csv_path: Path) -> tuple:
    stats = {
        "total": 0, "valid": 0, "missing_image_id": 0,
        "missing_camera_name": 0, "missing_date": 0,
        "missing_time": 0, "missing_ml": 0,
        "has_animal": 0, "is_blank": 0, "with_species": 0,
        "cameras": Counter(), "dates": Counter(),
    }
    issues = []
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            stats["total"] += 1
            row_issues = []
            
            if not row.get("image_id"):
                stats["missing_image_id"] += 1
                row_issues.append("missing_image_id")
            
            if not row.get("camera_name"):
                stats["missing_camera_name"] += 1
                row_issues.append("missing_camera_name")
            else:
                stats["cameras"][row["camera_name"]] += 1
            
            if not row.get("date"):
                stats["missing_date"] += 1
                row_issues.append("missing_date")
            else:
                date = row["date"][:7] if len(row["date"]) >= 7 else row["date"]
                stats["dates"][date] += 1
            
            if not row.get("time"):
                stats["missing_time"] += 1
                row_issues.append("missing_time")
            
            has_animal = row.get("has_animal", "").strip()
            is_blank = row.get("is_blank", "").strip()
            
            if has_animal == "" and is_blank == "":
                stats["missing_ml"] += 1
            else:
                if has_animal == "1":
                    stats["has_animal"] += 1
                if is_blank == "1":
                    stats["is_blank"] += 1
            
            if row.get("species", "").strip():
                stats["with_species"] += 1
            
            if not row_issues:
                stats["valid"] += 1
            else:
                issues.append({"row": i, "image_id": row.get("image_id", ""), "issues": row_issues})
    
    return stats, issues


def check_manifest_coverage(output_path: Path, manifest_path: Path) -> tuple:
    if not manifest_path.exists():
        return 0, 0, []
    
    manifest_ids = set()
    with open(manifest_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fid = row.get("file_id", "")
            if fid:
                manifest_ids.add(fid)
    
    output_ids = set()
    with open(output_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fid = row.get("image_id", "")
            if fid:
                output_ids.add(fid)
    
    missing = manifest_ids - output_ids
    return len(manifest_ids), len(output_ids), list(missing)[:10]


def main():
    print("=" * 60)
    print("WILDLIFE PIPELINE OUTPUT VALIDATION")
    print("=" * 60)
    
    if not OUTPUT_CSV.exists():
        print(f"\n[ERROR] Output file not found: {OUTPUT_CSV}")
        print("Run the pipeline first: python scripts/run_pipeline.py")
        sys.exit(1)
    
    print(f"\nValidating: {OUTPUT_CSV}")
    
    with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        actual_columns = reader.fieldnames or []
    
    print(f"\n" + "-" * 40)
    print("COLUMN VALIDATION")
    print("-" * 40)
    
    cols_ok, missing, extra = validate_columns(actual_columns)
    
    print(f"Required columns: {len(REQUIRED_COLUMNS)}")
    print(f"Actual columns: {len(actual_columns)}")
    
    if cols_ok:
        print("[OK] All required columns present")
    else:
        print(f"[ERROR] Missing columns: {missing}")
    
    if extra:
        print(f"[INFO] Extra columns: {extra}")
    
    print(f"\n" + "-" * 40)
    print("ROW VALIDATION")
    print("-" * 40)
    
    stats, issues = validate_rows(OUTPUT_CSV)
    
    print(f"Total rows: {stats['total']}")
    print(f"Valid rows: {stats['valid']} ({stats['valid']/max(stats['total'],1)*100:.1f}%)")
    
    print(f"\nData completeness:")
    print(f"  - With image_id: {stats['total'] - stats['missing_image_id']}")
    print(f"  - With camera_name: {stats['total'] - stats['missing_camera_name']}")
    print(f"  - With date: {stats['total'] - stats['missing_date']}")
    print(f"  - With time: {stats['total'] - stats['missing_time']}")
    print(f"  - With ML classification: {stats['total'] - stats['missing_ml']}")
    
    print(f"\nML Results:")
    print(f"  - Animals detected: {stats['has_animal']}")
    print(f"  - Blank images: {stats['is_blank']}")
    print(f"  - With species: {stats['with_species']}")
    
    if stats["cameras"]:
        print(f"\nCamera distribution (top 5):")
        for cam, count in stats["cameras"].most_common(5):
            print(f"  - {cam}: {count}")
    
    print(f"\n" + "-" * 40)
    print("MANIFEST COVERAGE")
    print("-" * 40)
    
    manifest_count, output_count, missing_ids = check_manifest_coverage(OUTPUT_CSV, MANIFEST)
    
    if manifest_count > 0:
        coverage = output_count / manifest_count * 100
        print(f"Manifest files: {manifest_count}")
        print(f"Output rows: {output_count}")
        print(f"Coverage: {coverage:.1f}%")
    
    print(f"\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
    all_ok = cols_ok and stats["valid"] == stats["total"]
    
    if all_ok:
        print("[OK] All validations passed!")
    else:
        if not cols_ok:
            print(f"[ERROR] Missing required columns: {missing}")
        if stats["valid"] < stats["total"]:
            print(f"[WARN] {stats['total'] - stats['valid']} rows have issues")
        if stats["missing_ml"] > 0:
            print(f"[INFO] {stats['missing_ml']} rows missing ML classification (run MegaDetector)")
    
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
