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
from pathlib import Path

# make imports like "from scripts.config import ..." work reliably
REPO_ROOT = Path(__file__).resolve().parents[2]  # .../UCI-NATURE
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.chdir(REPO_ROOT)  # ensure relative paths like data/... work

PYTHON = sys.executable
STAGING_DIR = Path("data/staging")


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


def prepare_staging_for_manual_mode(args: argparse.Namespace) -> None:
    """
    Manual Mode (process selected folder only)

    If --folder is provided, we copy that folder into data/staging so downstream
    steps (make_manifest, speciesnet, etc.) operate on ONLY that folder.
    """
    if not args.folder:
        return

    src = Path(args.folder).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"Manual folder not found: {src}")

    # Reset staging
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    if src.is_file():
        # single file
        shutil.copy2(src, STAGING_DIR / src.name)
    else:
        # directory: copy contents into staging
        # copytree() needs a non-existing dst, so copy children instead
        for child in src.iterdir():
            dst = STAGING_DIR / child.name
            if child.is_dir():
                shutil.copytree(child, dst)
            else:
                shutil.copy2(child, dst)

    print(f"[Manual Mode] Copied '{src}' -> '{STAGING_DIR}'")


def build_steps(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    """
    Auto Mode:
      - index drive
      - download images
      - run the rest of pipeline

    Manual Mode:
      - skip index + download
      - assumes data/staging contains ONLY the selected folder/files
    """
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
            ("Index Drive",     index_cmd),
            ("Download Images", download_cmd),
        ]

    # Create manifest always runs (both modes)
    steps.append(("Create Manifest", [PYTHON, "scripts/pipeline/make_manifest.py"]))

    # ML steps depend on provider
    if args.ml_provider == "speciesnet":
        steps.append(("Run SpeciesNet", [PYTHON, "scripts/ml/run_speciesnet.py"]))
        steps.append(("Parse ML Results", [PYTHON, "scripts/ml/run_inference.py", "--provider", "speciesnet"]))
    else:
        steps.append(("Run MegaDetector", [PYTHON, "scripts/ml/run_megadetector.py"]))
        steps.append(("Parse ML Results", [PYTHON, "scripts/ml/run_inference.py", "--provider", "megadetector"]))

    # Remaining pipeline steps
    steps += [
        ("Extract Metadata",     [PYTHON, "scripts/pipeline/extract_metadata.py"]),
        ("Generate Output CSVs", [PYTHON, "scripts/pipeline/make_output.py"]),
    ]

    return steps


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
    # Prepend repo root to PYTHONPATH (don’t clobber existing)
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(REPO_ROOT) + (os.pathsep + current if current else "")
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the wildlife pipeline end-to-end.")
    # run modes
    parser.add_argument("--mode", default="auto", choices=["auto", "manual"],
                        help="Auto: index+download+process. Manual: process selected folder only.")
    parser.add_argument("--folder", default=None,
                        help="Manual mode only: local folder/file to copy into data/staging before processing.")

    # ML provider
    parser.add_argument("--ml_provider", default="speciesnet", choices=["speciesnet", "megadetector"],
                        help="Which ML provider to run. (SpeciesNet includes species labels; MegaDetector is detection-only.)")

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

    # staging cleanup
    parser.add_argument("--no_prompt_cleanup", action="store_true", help="Never prompt to delete staging.")
    parser.add_argument("--cleanup_staging", action="store_true", help="Auto-delete staging at end (no prompt).")

    args = parser.parse_args()

    print(f"Repo root: {REPO_ROOT}")
    print(f"Using Python: {PYTHON}")
    print(f"Python version: {sys.version.split()[0]}")

    ensure_python_311()

    if args.mode == "manual":
        prepare_staging_for_manual_mode(args)

    print("=" * 60)
    print("WILDLIFE CAMERA IMAGE PROCESSING PIPELINE")
    print("=" * 60)

    steps = build_steps(args)
    env = make_subprocess_env()

    total_start = time.time()
    results: list[tuple[str, bool, float]] = []

    try:
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

    except KeyboardInterrupt:
        print("\nInterrupted by user. Stopping pipeline gracefully.")
        # do not raise; just continue to summary

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

    # If user interrupted before any step finished, exit cleanly
    if not results:
        print("\nNo steps completed.")
        sys.exit(0)

    # Optional cleanup
    if STAGING_DIR.exists():
        staging_size = sum(f.stat().st_size for f in STAGING_DIR.rglob("*") if f.is_file())
        staging_mb = staging_size / (1024 * 1024)

        if staging_mb > 1:
            if args.cleanup_staging:
                shutil.rmtree(STAGING_DIR)
                STAGING_DIR.mkdir(parents=True, exist_ok=True)
                print(f"\nCleared {staging_mb:.0f} MB from {STAGING_DIR}")
            elif not args.no_prompt_cleanup:
                print(f"\nStaging directory: {staging_mb:.0f} MB")
                response = input("Delete staging images to free disk space? [y/N]: ").strip().lower()
                if response == "y":
                    shutil.rmtree(STAGING_DIR)
                    STAGING_DIR.mkdir(parents=True, exist_ok=True)
                    print(f"  Cleared {staging_mb:.0f} MB from {STAGING_DIR}")
                else:
                    print("  Keeping staging images.")


if __name__ == "__main__":
    main()
