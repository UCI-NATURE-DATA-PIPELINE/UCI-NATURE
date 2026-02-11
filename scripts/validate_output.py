# Validates the per-location CSV outputs from make_output.py

import csv
import sys
from pathlib import Path
from collections import Counter

OUTPUT_DIR = Path("data/outputs/by_location")

REQUIRED_COLUMNS = [
    "CameraName",
    "DeploymentFolder",
    "Image#",
    "Species",
    "# of Individuals",
    "Date",
    "Time",
    "has_animal",
    "model_certainty",
    "Notes",
]


def validate_csv(csv_path: Path) -> dict:
    """Validate a single output CSV and return stats."""
    stats = {
        "total": 0, "with_date": 0, "with_species": 0,
        "animals": 0, "species": Counter(),
    }
    column_issues = []

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        actual_cols = reader.fieldnames or []

        missing = [c for c in REQUIRED_COLUMNS if c not in actual_cols]
        if missing:
            column_issues = missing

        for row in reader:
            stats["total"] += 1

            if row.get("Date"):
                stats["with_date"] += 1

            species = row.get("Species", "").strip()
            if species:
                stats["with_species"] += 1
                stats["species"][species] += 1

            if row.get("has_animal") == "1":
                stats["animals"] += 1

    return {"stats": stats, "column_issues": column_issues}


def main():
    print("=" * 60)
    print("WILDLIFE PIPELINE OUTPUT VALIDATION")
    print("=" * 60)

    if not OUTPUT_DIR.exists():
        print(f"\n[ERROR] Output directory not found: {OUTPUT_DIR}")
        print("Run the pipeline first: python scripts/run_pipeline.py")
        sys.exit(1)

    csv_files = sorted(OUTPUT_DIR.glob("*.csv"))
    if not csv_files:
        print(f"\n[ERROR] No CSV files found in {OUTPUT_DIR}")
        sys.exit(1)

    print(f"\nFound {len(csv_files)} location CSV(s) in {OUTPUT_DIR}\n")

    total_rows = 0
    total_species = 0
    all_species = Counter()
    all_ok = True

    for csv_path in csv_files:
        result = validate_csv(csv_path)
        stats = result["stats"]
        issues = result["column_issues"]

        total_rows += stats["total"]
        total_species += stats["with_species"]
        all_species.update(stats["species"])

        status = "[OK]" if not issues else "[WARN]"
        if issues:
            all_ok = False

        print(f"  {status} {csv_path.name}: {stats['total']} rows, "
              f"{stats['with_species']} with species, "
              f"{stats['with_date']} with date")

        if issues:
            print(f"       Missing columns: {issues}")

    print(f"\n" + "-" * 40)
    print(f"SUMMARY")
    print(f"-" * 40)
    print(f"Total rows across all files: {total_rows}")
    print(f"With species classification: {total_species}")

    if all_species:
        print(f"\nSpecies distribution:")
        for species, count in all_species.most_common():
            print(f"  {species}: {count}")

    if all_ok:
        print(f"\n[OK] All validations passed!")
    else:
        print(f"\n[WARN] Some files have issues (see above)")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
