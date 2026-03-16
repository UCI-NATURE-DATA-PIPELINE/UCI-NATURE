# scripts/pipeline/run_pipeline.py

import argparse
import os
import shutil
import subprocess
import sys
import time
import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.chdir(REPO_ROOT)

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
        print("ERROR: This pipeline must be run with Python 3.11 to match dependencies.")
        print(f"Current Python: {sys.version}")
        sys.exit(1)


def run_step(name: str, cmd: list[str]) -> None:
    print("\n" + "=" * 80)
    print(f"STEP: {name}")
    print("CMD:", " ".join(cmd))
    print("=" * 80)
    res = subprocess.run(cmd, text=True)
    if res.returncode != 0:
        print(f"\nERROR: Step failed: {name} (exit code {res.returncode})")
        sys.exit(res.returncode)


def copy_staging_backup() -> None:
    if not STAGING_DIR.exists():
        return
    STAGING_BACKUP.parent.mkdir(parents=True, exist_ok=True)
    if STAGING_BACKUP.exists():
        shutil.rmtree(STAGING_BACKUP)
    shutil.copytree(STAGING_DIR, STAGING_BACKUP)


def restore_staging_backup() -> None:
    if not STAGING_BACKUP.exists():
        return
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    shutil.copytree(STAGING_BACKUP, STAGING_DIR)


def manifest_has_rows(path: str) -> bool:
    p = Path(path)
    if not p.exists():
        return False
    try:
        with p.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for _ in reader:
                return True
    except Exception:
        return False
    return False


def build_steps(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
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

    manifest_to_process = args.new_manifest if (args.mode == "auto" and args.use_new_manifest_for_outputs) else "data/outputs/manifest.csv"
    if args.mode == "auto" and args.use_new_manifest_for_outputs and not manifest_has_rows(manifest_to_process):
        manifest_to_process = "data/outputs/manifest.csv"

    # Extract EXIF metadata before SpeciesNet postprocessing so that
    # postprocess_speciesnet.py has metadata.csv available for burst timestamp grouping.
    steps.append(("Extract Metadata (EXIF)", [PYTHON, "scripts/pipeline/extract_metadata.py", "--manifest", manifest_to_process]))

    steps.append(("Run SpeciesNet", [PYTHON, "scripts/ml/run_speciesnet.py"]))
    steps.append(("Postprocess SpeciesNet", [PYTHON, "scripts/ml/postprocess_speciesnet.py", "--burst_window", str(args.ml_burst_window)]))
    steps.append(("Parse ML Results", [PYTHON, "scripts/ml/run_inference.py", "--provider", "speciesnet"]))

    # Re-run extract_metadata now that ml_outputs.csv exists so the final
    # metadata.csv has ML columns (species, has_animal, model_certainty) merged in.
    steps.append(("Extract Metadata (merge ML)", [PYTHON, "scripts/pipeline/extract_metadata.py", "--manifest", manifest_to_process]))

    steps.append(("Generate Output CSVs", [
        PYTHON, "scripts/pipeline/make_output.py",
        "--manifest", manifest_to_process,
        "--burst_seconds", str(args.burst_seconds),
        "--burst_export", args.burst_export
    ]))

    if args.upload:
        upload_cmd = [PYTHON, "scripts/drive_upload/upload_to_drive.py"]
        if args.overwrite:
            upload_cmd += ["--overwrite"]
        steps.append(("Upload Results to Drive", upload_cmd))

    return steps


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the wildlife pipeline end-to-end.")

    parser.add_argument("--mode", default="auto", choices=["auto", "manual"],
                        help="Auto: index+download+process NEW images with caching. Manual: process selected folder only.")
    parser.add_argument("--folder", default=None,
                        help="Manual mode only: local folder path of images to stage.")

    parser.add_argument("--drive_root", default=None, help="Drive root folder ID (auto mode).")
    parser.add_argument("--start_folders", default=None, help="Comma-separated folder IDs to start indexing from.")
    parser.add_argument("--index", default=None, help="Use an existing drive index CSV instead of building one.")
    parser.add_argument("--out_index", default=None, help="Output drive index CSV path.")
    parser.add_argument("--per_folder", action="store_true", help="Name index output using folder tag.")
    parser.add_argument("--resume", action="store_true", help="Resume download/index (auto mode).")
    parser.add_argument("--max_files", type=int, default=None, help="Max files to index (auto mode).")
    parser.add_argument("--max_downloads", type=int, default=None, help="Max files to download (auto mode).")

    parser.add_argument("--batch_size", type=int, default=0, help="Optional batch manifest size (>0 to write batches).")
    parser.add_argument("--cache", default="data/outputs/cache/processed_file_ids.txt", help="Cache file to track processed file_ids.")
    parser.add_argument("--new_manifest", default="data/outputs/manifest_new.csv", help="Output path for new-only manifest.")
    parser.add_argument("--use_new_manifest_for_outputs", action="store_true",
                        help="Use new-only manifest for metadata+output steps (falls back if empty).")

    parser.add_argument("--ml_burst_window", type=int, default=300, help="Burst window seconds for SpeciesNet postprocess.")
    parser.add_argument("--burst_seconds", type=int, default=300, help="Burst duration seconds for output.")
    parser.add_argument("--burst_export", default="all", choices=["all", "first", "middle", "last"],
                        help="Which burst images to export in output.")

    parser.add_argument("--upload", action="store_true",
                        help="Upload output CSVs to Google Drive after pipeline completes (production).")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing Drive CSVs instead of appending (used with --upload).")

    args = parser.parse_args()

    ensure_python_311()

    if args.mode == "manual":
        if not args.folder:
            print("ERROR: --folder is required in manual mode.")
            sys.exit(2)
        src = Path(args.folder)
        if not src.exists():
            print(f"ERROR: Folder does not exist: {src}")
            sys.exit(2)
        STAGING_DIR.mkdir(parents=True, exist_ok=True)
        for p in src.glob("*"):
            if p.is_file():
                shutil.copy2(p, STAGING_DIR / p.name)

    if args.mode == "manual":
        copy_staging_backup()

    steps = build_steps(args)
    start = time.time()
    for name, cmd in steps:
        run_step(name, cmd)
    elapsed = time.time() - start
    print(f"\nDONE in {elapsed/60:.1f} minutes")

    if args.mode == "manual":
        restore_staging_backup()
    else:
        # Auto mode: clear staging after a successful run to free disk space.
        # Re-downloads are prevented by data/outputs/.download_progress.csv.
        if STAGING_DIR.exists():
            shutil.rmtree(STAGING_DIR)
            print(f"Cleared {STAGING_DIR} (outputs preserved in data/outputs/)")


if __name__ == "__main__":
    main()