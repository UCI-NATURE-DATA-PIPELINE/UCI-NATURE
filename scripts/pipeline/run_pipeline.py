# runs the pipeline in the correct order:
# index > download > manifest > speciesnet > inference > metadata > output
#
# SpeciesNet runs MegaDetector internally, so we only need one ML step.
#
# IMPORTANT: Run this from your .venv so all steps use Python 3.11:
#   source .venv/bin/activate
#   python scripts/pipeline/run_pipeline.py

import argparse
import os
import shutil
import subprocess
import sys
import time
import csv
from pathlib import Path

# make imports like "from scripts.config import ..." work reliably
REPO_ROOT = Path(__file__).resolve().parents[2]  # .../UCI-NATURE
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.chdir(REPO_ROOT)  # ensure relative paths like data/... work

PYTHON = sys.executable
STAGING_DIR = Path("data/staging")
STAGING_BACKUP = Path("data/staging_full_backup")


def parse_id_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


def make_run_tag(drive_root: str | None, start_folders: str | None) -> str:
    ids = parse_id_list(start_folders)
    if ids:
        return "_".join(ids)
    return drive_root or ""


def infer_index_path(args: argparse.Namespace) -> str:
    # priority: explicit index path > explicit out_index > derived per-folder index > default
    if args.index:
        return args.index
    if args.out_index:
        return args.out_index
    if args.per_folder:
        tag = make_run_tag(args.drive_root, args.start_folders)
        if tag:
            return str(Path("data/outputs") / f"drive_index_{tag}.csv")
    return "data/outputs/drive_index.csv"


def ensure_python_311() -> None:
    if sys.version_info[:2] != (3, 11):
        print("\n[ERROR] Wrong Python version.")
        print(f"Using: {sys.version.split()[0]}")
        print("SpeciesNet requires Python 3.11.")
        print("Activate your venv first:")
        print("  source .venv/bin/activate")
        print("  python scripts/pipeline/run_pipeline.py")
        sys.exit(1)


def make_subprocess_env() -> dict[str, str]:
    """
    Ensure child processes can import `scripts.*` no matter how the script is launched.
    """
    env = os.environ.copy()
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(REPO_ROOT) + (os.pathsep + current if current else "")
    return env


def prepare_staging_for_manual_mode(folder: str) -> None:
    """
    Manual Mode: copy provided folder/file into data/staging so the pipeline processes ONLY it.
    """
    src = Path(folder).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"Manual folder not found: {src}")

    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    if src.is_file():
        shutil.copy2(src, STAGING_DIR / src.name)
    else:
        for child in src.iterdir():
            dst = STAGING_DIR / child.name
            if child.is_dir():
                shutil.copytree(child, dst)
            else:
                shutil.copy2(child, dst)

    print(f"[Manual Mode] Copied '{src}' -> '{STAGING_DIR}'")


def _rows_in_manifest(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, "r", encoding="utf-8") as f:
        return max(0, sum(1 for _ in f) - 1)


def prepare_staging_for_auto_new(manifest_new: Path) -> None:
    """
    Auto Mode caching:
    - Move current data/staging -> data/staging_full_backup
    - Recreate data/staging with ONLY files listed in manifest_new
    - After pipeline finishes, we restore staging in finally-block
    """
    if STAGING_BACKUP.exists():
        shutil.rmtree(STAGING_BACKUP)

    if STAGING_DIR.exists():
        shutil.move(str(STAGING_DIR), str(STAGING_BACKUP))

    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    # Copy only new files from backup into staging
    with open(manifest_new, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "local_path" not in reader.fieldnames:
            raise ValueError(f"{manifest_new} is missing local_path column")

        copied = 0
        missing = 0

        for r in reader:
            lp = (r.get("local_path") or "").strip()
            if not lp:
                continue

            # local_path is like "data/staging/Research Park/.../file.jpg"
            # map to backup root: data/staging_full_backup/Research Park/.../file.jpg
            p = Path(lp)
            parts = list(p.parts)

            # find "data/staging" in path parts
            try:
                idx = parts.index("data")
                if idx + 1 < len(parts) and parts[idx + 1] == "staging":
                    rel_parts = parts[idx + 2 :]
                else:
                    rel_parts = parts
            except ValueError:
                rel_parts = parts

            src = STAGING_BACKUP.joinpath(*rel_parts)
            dst = STAGING_DIR.joinpath(*rel_parts)
            dst.parent.mkdir(parents=True, exist_ok=True)

            if src.exists():
                shutil.copy2(src, dst)
                copied += 1
            else:
                missing += 1

        print(f"[Auto Mode] Prepared staging with new files: copied={copied}, missing={missing}")


def restore_staging_after_auto() -> None:
    """
    Restore original staging after auto new-only processing.
    """
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    if STAGING_BACKUP.exists():
        shutil.move(str(STAGING_BACKUP), str(STAGING_DIR))


def build_steps(args: argparse.Namespace, manifest_to_process: str) -> list[tuple[str, list[str]]]:
    steps: list[tuple[str, list[str]]] = []

    if args.mode == "auto":
        index_cmd = [PYTHON, "scripts/pipeline/build_index.py"]
        if args.drive_root:
            index_cmd += ["--drive_root", args.drive_root]
        if args.start_folders:
            index_cmd += ["--start_folders", args.start_folders]
        if args.out_index:
            index_cmd += ["--out", args.out_index]
        if args.per_folder:
            index_cmd += ["--per_folder"]
        if args.resume:
            index_cmd += ["--resume"]
        if args.max_files is not None:
            index_cmd += ["--max_files", str(args.max_files)]

        download_cmd = [PYTHON, "scripts/pipeline/download_drive.py", "--index", infer_index_path(args)]
        if args.resume:
            download_cmd += ["--resume"]
        if args.max_downloads is not None:
            download_cmd += ["--max_downloads", str(args.max_downloads)]

        steps += [
            ("Index Drive", index_cmd),
            ("Download Images", download_cmd),
        ]

    # Create manifest
    if args.mode == "auto":
        steps.append((
            "Create Manifest (new-only)",
            [PYTHON, "scripts/pipeline/make_manifest.py",
             "--cache", args.cache,
             "--new_out", args.new_manifest,
             "--write_new_only",
             "--batch_size", str(args.batch_size)]
        ))
    else:
        steps.append(("Create Manifest", [
            PYTHON, "scripts/pipeline/make_manifest.py",
            "--batch_size", str(args.batch_size)
        ]))

    # SpeciesNet + parse results
    steps.append(("Run SpeciesNet", [PYTHON, "scripts/ml/run_speciesnet.py"]))
    steps.append(("Postprocess SpeciesNet", [PYTHON, "scripts/ml/postprocess_speciesnet.py", "--burst_window", str(args.ml_burst_window)]))
    steps.append(("Parse ML Results", [PYTHON, "scripts/ml/run_inference.py", "--provider", "speciesnet"]))

    # Remaining pipeline steps (use the manifest we chose)
    steps.append(("Extract Metadata", [PYTHON, "scripts/pipeline/extract_metadata.py", "--manifest", manifest_to_process]))
    steps.append(("Generate Output CSVs", [
        PYTHON, "scripts/pipeline/make_output.py",
        "--manifest", manifest_to_process,
        "--burst_seconds", str(args.burst_seconds),
        "--burst_export", args.burst_export
    ]))

    return steps


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the wildlife pipeline end-to-end.")

    parser.add_argument("--mode", default="auto", choices=["auto", "manual"],
                        help="Auto: index+download+process NEW images with caching. Manual: process selected folder only.")
    parser.add_argument("--folder", default=None,
                        help="Manual mode only: local folder/file to copy into data/staging before processing.")

    # SpeciesNet only (MegaDetector is inside it)
    parser.add_argument("--ml_provider", default="speciesnet", choices=["speciesnet"],
                        help="Only SpeciesNet is supported (it runs MegaDetector internally).")

    # build_index passthrough
    parser.add_argument("--drive_root", default=None, help="Drive root folder id (optional).")
    parser.add_argument("--start_folders", default=None, help="Comma-separated folder IDs to start from.")
    parser.add_argument("--out_index", default=None, help="Output drive_index.csv path.")
    parser.add_argument("--per_folder", action="store_true", help="Write per-folder index files.")
    parser.add_argument("--resume", action="store_true", help="Resume indexing/downloading if possible.")
    parser.add_argument("--max_files", type=int, default=None, help="Limit indexing rows for testing.")

    # download_drive passthrough
    parser.add_argument("--index", default=None, help="Explicit index path to download from.")
    parser.add_argument("--max_downloads", type=int, default=None, help="Limit downloads for testing.")

    # cache + new manifest
    parser.add_argument("--cache", default="data/outputs/cache/processed_file_ids.txt")
    parser.add_argument("--new_manifest", default="data/outputs/manifest_new.csv")

    # batch sizing
    parser.add_argument("--batch_size", type=int, default=0)

    # burst output controls
    parser.add_argument("--burst_seconds", type=int, default=10)
    parser.add_argument("--burst_export", choices=["all", "first"], default="first")

    # burst voting controls for SpeciesNet postprocess
    parser.add_argument("--ml_burst_window", type=int, default=300)

    args = parser.parse_args()

    args.burst_seconds = max(10, min(300, int(args.burst_seconds)))
    args.ml_burst_window = max(10, min(300, int(args.ml_burst_window)))
    if args.batch_size is None:
        args.batch_size = 0
    if args.batch_size < 0:
        args.batch_size = 0

    print(f"Repo root: {REPO_ROOT}")
    print(f"Using Python: {PYTHON}")
    print(f"Python version: {sys.version.split()[0]}")

    ensure_python_311()

    if args.mode == "manual":
        if not args.folder:
            raise ValueError("Manual mode requires --folder")
        prepare_staging_for_manual_mode(args.folder)
        manifest_to_process = "data/outputs/manifest.csv"
    else:
        manifest_to_process = args.new_manifest

    print("=" * 60)
    print("WILDLIFE CAMERA IMAGE PROCESSING PIPELINE")
    print("=" * 60)

    env = make_subprocess_env()

    try:
        steps = build_steps(args, manifest_to_process)

        total_start = time.time()
        results: list[tuple[str, bool, float]] = []

        for i, (name, cmd) in enumerate(steps, 1):
            print(f"\n[Step {i}/{len(steps)}] {name}")
            print("-" * 40)
            print(" ".join(cmd))

            start = time.time()
            result = subprocess.run(cmd, env=env)
            duration = time.time() - start

            success = result.returncode == 0
            results.append((name, success, duration))

            if success:
                print(f"  [OK] {name} ({duration:.1f}s)")
            else:
                print(f"  [FAILED] {name} (exit code {result.returncode})")
                print(f"Stopped due to error on: {name}")
                break

            # After creating manifest_new in auto mode, if 0 rows -> exit cleanly
            if args.mode == "auto" and name.startswith("Create Manifest"):
                n_new = _rows_in_manifest(Path(args.new_manifest))
                if n_new == 0:
                    print(f"\n[OK] No new images to process (0 rows in {args.new_manifest}).")
                    return

                # Prepare staging to contain ONLY new images for SpeciesNet run
                prepare_staging_for_auto_new(Path(args.new_manifest))

        total_duration = time.time() - total_start

        print("\n" + "=" * 60)
        print("PIPELINE SUMMARY")
        print("=" * 60)

        for name, success, duration in results:
            status = "[OK]" if success else "[FAILED]"
            print(f"  {status} {name}: {duration:.1f}s")

        print(f"\nTotal time: {total_duration:.1f}s ({total_duration/60:.1f} min)")

        if results and not all(success for _, success, _ in results):
            sys.exit(1)

        if not results:
            print("\nNo steps completed.")
            sys.exit(0)

        # Auto mode: update cache ONLY AFTER SUCCESS
        if args.mode == "auto":
            update_cmd = [
                PYTHON, "scripts/pipeline/make_manifest.py",
                "--cache", args.cache,
                "--new_out", args.new_manifest,
                "--write_new_only",
                "--update_cache",
                "--batch_size", str(args.batch_size)
            ]
            print("\nUpdating cache...")
            subprocess.run(update_cmd, env=env)

    finally:
        # Restore original staging after auto run (so user’s staging isn’t destroyed)
        if args.mode == "auto" and STAGING_BACKUP.exists():
            restore_staging_after_auto()


if __name__ == "__main__":
    main()