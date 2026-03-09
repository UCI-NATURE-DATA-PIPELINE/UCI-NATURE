# creates manifest.csv from local downloaded images in data/staging/
# optionally creates batch manifests in data/outputs/batches/

import csv
import argparse
from datetime import datetime
from pathlib import Path

STAGING = Path("data/staging")
OUT = Path("data/outputs/manifest.csv")
BATCH_DIR = Path("data/outputs/batches")

CACHE = Path("data/outputs/cache/processed_file_ids.txt")
NEW_OUT = Path("data/outputs/manifest_new.csv")


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

    # Auto-mode caching helpers
    parser.add_argument("--cache", default=str(CACHE), help="file with processed file_ids (one per line)")
    parser.add_argument("--new_out", default=str(NEW_OUT), help="where to write manifest of only new/unprocessed ids")
    parser.add_argument("--write_new_only", action="store_true", help="also write a filtered manifest containing only new/unprocessed file_ids")
    parser.add_argument("--update_cache", action="store_true", help="append new_out file_ids to cache (run only AFTER a successful pipeline run)")
    args = parser.parse_args()

    staging = Path(args.staging)
    out = Path(args.out)
    batch_size = args.batch_size
    batch_dir = Path(args.batch_dir)

    cache_path = Path(args.cache)
    new_out = Path(args.new_out)

    if not staging.exists():
        raise FileNotFoundError(f"{staging} not found. Run download_drive.py first.")

    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"}

    rows = []
    for p in sorted(staging.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix not in IMAGE_EXTENSIONS:
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

    if args.write_new_only:
        processed = set()
        if cache_path.exists():
            with open(cache_path, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s:
                        processed.add(s)

        new_rows = []
        skipped = 0
        for r in rows:
            fid = (r.get("file_id") or "").strip()
            if not fid:
                skipped += 1
                continue
            if fid in processed:
                skipped += 1
                continue
            new_rows.append(r)

        write_csv(new_out, new_rows, fieldnames)
        print(f"cache: {cache_path} ({len(processed)} ids)")
        print(f"wrote {len(new_rows)} rows -> {new_out}")
        print(f"skipped {skipped} rows (already processed or missing file_id)")

        if args.update_cache:
            # SAFE cache update: append ONLY ids from new_out, and dedupe
            cache_path.parent.mkdir(parents=True, exist_ok=True)

            existing = set(processed)
            appended = 0
            with open(cache_path, "a", encoding="utf-8") as f:
                for r in new_rows:
                    fid = (r.get("file_id") or "").strip()
                    if fid and fid not in existing:
                        existing.add(fid)
                        f.write(fid + "\n")
                        appended += 1

            print(f"updated cache: appended {appended} ids -> {cache_path}")


if __name__ == "__main__":
    main()