# creates manifest.csv from local downloaded images in data/staging/

import csv
from datetime import datetime
from pathlib import Path

STAGING = Path("data/staging")
OUT = Path("data/outputs/manifest.csv")


def split_local_name(local_file_name: str):
    # expected "<file_id>__<original_name>"
    if "__" in local_file_name:
        file_id, original_name = local_file_name.split("__", 1)
        return file_id, original_name
    return "", local_file_name


def main():
    if not STAGING.exists():
        raise FileNotFoundError("data/staging not found. Run download_drive.py first.")

    OUT.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for p in sorted(STAGING.rglob("*")):
        if not p.is_file():
            continue

        file_id, original_name = split_local_name(p.name)

        rows.append({
            "file_id": file_id,                 # drive ID
            "file_name": original_name,         # original filename
            "local_file_name": p.name,          # what gets saved locally
            "local_path": str(p),
            "size_bytes": p.stat().st_size,
            "modified_time": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
        })

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["file_id", "file_name", "local_file_name", "local_path", "size_bytes", "modified_time"],
        )
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()