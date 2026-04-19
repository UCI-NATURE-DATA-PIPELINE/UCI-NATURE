from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.chdir(REPO_ROOT)

from scripts.pipeline.pipeline_service import (  # noqa: E402
    PipelineRunConfig,
    ensure_python_311,
    resolve_pipeline_staging_dir,
    run_pipeline_service,
)

PYTHON = sys.executable
STAGING_DIR = Path("data/staging")


def resolve_repo_path(path_value: Optional[str]) -> Optional[Path]:
    if not path_value:
        return None
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (REPO_ROOT / path).resolve()


def parse_id_list(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


def make_run_tag(drive_root: Optional[str], start_folders: Optional[str]) -> str:
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


def run_step(name: str, cmd: list[str]) -> None:
    print("\n" + "=" * 80, flush=True)
    print(f"STEP: {name}", flush=True)
    print("CMD:", " ".join(cmd), flush=True)
    print("=" * 80, flush=True)
    child_env = os.environ.copy()
    child_env.setdefault("PYTHONUNBUFFERED", "1")
    res = subprocess.run(cmd, text=True, cwd=str(REPO_ROOT), env=child_env)
    if res.returncode != 0:
        raise RuntimeError(f"Step failed: {name} (exit code {res.returncode})")


def warn_missing_dependencies(args: argparse.Namespace) -> None:
    if importlib.util.find_spec("PIL") is None:
        print(
            "WARNING: Pillow is not installed in this Python environment; "
            "extract_metadata.py will write metadata.csv but EXIF/dimensions will be blank.",
            flush=True,
        )

    if importlib.util.find_spec("speciesnet") is None:
        print(
            "WARNING: speciesnet is not installed in this Python environment; "
            "the pipeline will fail at the SpeciesNet step until that dependency is installed.",
            flush=True,
        )

    if args.mode == "auto" and importlib.util.find_spec("googleapiclient") is None:
        print(
            "WARNING: googleapiclient is not installed in this Python environment; "
            "auto-mode Drive indexing/downloading will fail until that dependency is installed.",
            flush=True,
        )


def run_pipeline_direct(config: Optional[PipelineRunConfig] = None) -> dict:
    return run_pipeline_service(config or PipelineRunConfig())


def resolve_source_root(args: argparse.Namespace) -> tuple[str, Path]:
    default_staging = resolve_pipeline_staging_dir(STAGING_DIR)

    if args.mode == "auto":
        return "google_drive", default_staging

    if args.mode == "staging":
        source_root = resolve_repo_path(args.folder) or default_staging
        if not source_root.exists():
            raise FileNotFoundError(f"Staging folder does not exist: {source_root}")
        return "existing_staging", source_root

    if not args.folder:
        raise ValueError("--folder is required in manual mode.")

    source_root = resolve_repo_path(args.folder)
    if source_root is None or not source_root.exists():
        raise FileNotFoundError(f"Folder does not exist: {args.folder}")

    if source_root.resolve() == default_staging.resolve():
        return "existing_staging", source_root

    return "direct_local_folder", source_root


def prepare_google_drive_source(args: argparse.Namespace) -> Path:
    index_path = infer_index_path(args)

    if not args.index:
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
        run_step("Index Drive", index_cmd)

    download_cmd = [
        PYTHON,
        "scripts/pipeline/download_drive.py",
        "--index",
        index_path,
    ]
    if args.resume:
        download_cmd += ["--resume"]
    if args.max_downloads is not None:
        download_cmd += ["--max_downloads", str(args.max_downloads)]
    run_step("Download Images", download_cmd)

    resolved_index_path = resolve_repo_path(index_path)
    if resolved_index_path is None:
        raise RuntimeError("Unable to resolve drive index path.")
    return resolved_index_path


def resolve_drive_index_for_run(
    args: argparse.Namespace,
    source_mode: str,
    source_root: Path,
) -> Optional[Path]:
    if source_mode == "google_drive":
        return resolve_repo_path(infer_index_path(args))

    if source_mode == "existing_staging":
        if args.index:
            return resolve_repo_path(args.index)

        default_staging = resolve_pipeline_staging_dir(STAGING_DIR)
        candidate = resolve_repo_path(infer_index_path(args))
        if (
            source_root.resolve() == default_staging.resolve()
            and candidate is not None
            and candidate.exists()
        ):
            return candidate

    return None


def run_upload_step(args: argparse.Namespace) -> None:
    upload_cmd = [
        PYTHON,
        "scripts/drive_upload/upload_to_drive.py",
        "--mode",
        "dynamic",
    ]
    if args.overwrite:
        upload_cmd += ["--overwrite"]
    if args.upload_as_csv:
        upload_cmd += ["--as-csv"]
    if args.legacy_map:
        upload_cmd += ["--legacy-map", args.legacy_map]
    run_step("Upload Results to Drive", upload_cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the wildlife pipeline end-to-end.")

    parser.add_argument(
        "--mode",
        default="auto",
        choices=["auto", "manual", "staging"],
        help=(
            "auto: Google Drive index+download flow; "
            "manual: process a direct local folder path; "
            "staging: process an existing staging folder without copying."
        ),
    )
    parser.add_argument(
        "--folder",
        default=None,
        help=(
            "Source folder for manual mode, or optional staging folder path for staging mode. "
            "Manual mode now processes the provided folder directly."
        ),
    )

    parser.add_argument("--drive_root", default=None, help="Drive root folder ID (auto mode).")
    parser.add_argument(
        "--start_folders",
        default=None,
        help="Comma-separated folder IDs to start indexing from.",
    )
    parser.add_argument(
        "--index",
        default=None,
        help="Use an existing drive index CSV instead of building one.",
    )
    parser.add_argument("--out_index", default=None, help="Output drive index CSV path.")
    parser.add_argument(
        "--per_folder",
        action="store_true",
        help="Name index output using folder tag.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume download/index (auto mode).",
    )
    parser.add_argument(
        "--max_files",
        type=int,
        default=None,
        help="Max files to index (auto mode).",
    )
    parser.add_argument(
        "--max_downloads",
        type=int,
        default=None,
        help="Max files to download (auto mode).",
    )

    parser.add_argument(
        "--batch_size",
        type=int,
        default=0,
        help="Optional batch manifest size (>0 to write batches).",
    )
    parser.add_argument(
        "--speciesnet_batch_size",
        type=int,
        default=8,
        help="Actual SpeciesNet inference batch size.",
    )
    parser.add_argument(
        "--cache",
        default="data/outputs/cache/processed_file_ids.txt",
        help="Cache file to track processed file_ids.",
    )
    parser.add_argument(
        "--new_manifest",
        default="data/outputs/manifest_new.csv",
        help="Output path for the auto-mode new-only manifest.",
    )
    parser.add_argument(
        "--use_new_manifest_for_outputs",
        action="store_true",
        help="Legacy no-op. Auto mode now always processes the new-only manifest when rows exist.",
    )

    parser.add_argument(
        "--ml_burst_window",
        type=int,
        default=15,
        help="Burst window seconds for SpeciesNet postprocess.",
    )
    parser.add_argument(
        "--burst_seconds",
        type=int,
        default=15,
        help="Burst duration seconds for output.",
    )
    parser.add_argument(
        "--burst_export",
        default="all",
        choices=["all", "first"],
        help="Which burst images to export in output.",
    )
    parser.add_argument(
        "--exclude_humans",
        action="store_true",
        help="Exclude human-only rows from final output CSVs.",
    )

    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload output CSVs to Google Drive after pipeline completes.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing Drive CSVs instead of appending.",
    )
    parser.add_argument(
        "--upload_as_csv",
        action="store_true",
        help="Create uploaded files as CSV instead of Google Sheets.",
    )
    parser.add_argument(
        "--legacy_map",
        default="",
        help="Optional legacy mapping CSV for upload script if needed.",
    )

    args = parser.parse_args()

    ensure_python_311()
    os.chdir(REPO_ROOT)
    print(f"Python executable: {PYTHON}", flush=True)
    print(f"Working directory: {REPO_ROOT}", flush=True)
    warn_missing_dependencies(args)

    source_mode, source_root = resolve_source_root(args)
    print(f"Resolved source mode: {source_mode}", flush=True)
    print(f"Resolved source root: {source_root}", flush=True)

    drive_index_path = (
        prepare_google_drive_source(args)
        if source_mode == "google_drive"
        else resolve_drive_index_for_run(args, source_mode, source_root)
    )

    config = PipelineRunConfig(
        manifest_batch_size=args.batch_size,
        speciesnet_batch_size=args.speciesnet_batch_size,
        exclude_humans=args.exclude_humans,
        ml_burst_window=args.ml_burst_window,
        burst_seconds=args.burst_seconds,
        burst_export=args.burst_export,
        staging_dir=source_root,
        drive_index_path=drive_index_path,
        cache_path=Path(args.cache),
        new_manifest_path=Path(args.new_manifest),
        process_new_only=(source_mode == "google_drive"),
        update_cache_on_success=(source_mode == "google_drive"),
    )

    start = time.time()
    result = run_pipeline_service(config)
    elapsed = time.time() - start
    print(f"\nDONE in {elapsed / 60:.1f} minutes")

    if args.upload and not result.get("skipped"):
        run_upload_step(args)

    if source_mode == "google_drive":
        resolved_staging_dir = resolve_pipeline_staging_dir(STAGING_DIR)
        if resolved_staging_dir.exists():
            shutil.rmtree(resolved_staging_dir)
            print(
                f"Cleared {resolved_staging_dir} (outputs preserved in data/outputs/)",
                flush=True,
            )


if __name__ == "__main__":
    main()
