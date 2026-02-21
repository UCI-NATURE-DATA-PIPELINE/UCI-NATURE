# creates manifest.csv from local downloaded images in data/staging/
# optionally creates batch manifests in data/outputs/batches/

import csv
import argparse
from datetime import datetime
from pathlib import Path

STAGING = Path("data/staging")
OUT = Path("data/outputs/manifest.csv")
BATCH_DIR = Path("data/outputs/batches")


def split_local_name(local_file_name: str):
    # expected "<file_id>__<original_name>"
    if "__" in local_file_name:
        file_id, original_name = local_file_name.split("__", 1)
        return file_id, original_name
    return "", local_file_name


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", default=str(STAGING))
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--batch_size", type=int, default=0, help="0 = no batch manifests")
    parser.add_argument("--batch_dir", default=str(BATCH_DIR))
    args = parser.parse_args()

    staging = Path(args.staging)
    out = Path(args.out)
    batch_size = args.batch_size
    batch_dir = Path(args.batch_dir)

    if not staging.exists():
        raise FileNotFoundError(f"{staging} not found. Run download_drive.py first.")

    rows = []
    for p in sorted(staging.rglob("*")):
        if not p.is_file():
            continue

        file_id, original_name = split_local_name(p.name)

        try:
            local_path = str(p.relative_to(Path.cwd()))
        except ValueError:
            local_path = str(p)

        rows.append({
            "file_id": file_id,
            "file_name": original_name,
            "local_file_name": p.name,
            "local_path": local_path,
            "size_bytes": p.stat().st_size,
            "modified_time": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
        })

    fieldnames = ["file_id", "file_name", "local_file_name", "local_path", "size_bytes", "modified_time"]
    write_csv(out, rows, fieldnames)
    print(f"wrote {len(rows)} rows -> {out}")

    # batch manifests
    if batch_size and batch_size > 0:
        batch_dir.mkdir(parents=True, exist_ok=True)
        total = len(rows)
        batch_count = (total + batch_size - 1) // batch_size

        for i in range(batch_count):
            start = i * batch_size
            end = min(start + batch_size, total)
            batch_rows = rows[start:end]
            batch_path = batch_dir / f"batch_{i+1:04d}.csv"
            write_csv(batch_path, batch_rows, fieldnames)
            print(f"  batch {i+1:04d}: {len(batch_rows)} rows -> {batch_path}")


if __name__ == "__main__":
    main()