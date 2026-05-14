from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Union

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.config import OUT_DIR as CONFIG_STAGING_DIR
from scripts.ml.postprocess_speciesnet import postprocess_speciesnet_results
from scripts.ml.run_inference import OUT_ML, SPECIESNET_JSON, run_speciesnet
from scripts.ml.run_speciesnet import run_speciesnet_model
from scripts.pipeline.extract_metadata import (
    OUT_CSV_DEFAULT as METADATA_CSV_DEFAULT,
    extract_metadata_from_manifest,
)
from scripts.pipeline.make_manifest import OUT as MANIFEST_DEFAULT, STAGING, build_manifest
from scripts.pipeline.make_output import generate_output_csvs

DEFAULT_STAGING_DIR = Path(CONFIG_STAGING_DIR or STAGING)


def _resolve_repo_path(path: Union[Path, str]) -> Path:
    path = Path(path)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _remove_stale_file(path: Union[Path, str], *, label: str) -> None:
    resolved_path = _resolve_repo_path(path)
    if not resolved_path.exists() or not resolved_path.is_file():
        return
    resolved_path.unlink()
    print(f"Removed stale {label}: {_display_path(resolved_path)}")


def resolve_pipeline_staging_dir(path: Optional[Union[Path, str]] = None) -> Path:
    return _resolve_repo_path(path or DEFAULT_STAGING_DIR)


@dataclass
class PipelineRunConfig:
    manifest_batch_size: int = 0
    speciesnet_batch_size: int = 8
    confidence_threshold: int = 80
    remove_burst_duplicates: bool = True
    exclude_humans: bool = True
    ml_burst_window: int = 300
    burst_seconds: int = 300
    burst_export: str = "all"
    staging_dir: Path = DEFAULT_STAGING_DIR
    manifest_path: Path = MANIFEST_DEFAULT
    metadata_path: Path = METADATA_CSV_DEFAULT
    ml_outputs_path: Path = OUT_ML
    speciesnet_json_path: Path = SPECIESNET_JSON


def ensure_python_311() -> None:
    if not ((3, 11) <= sys.version_info[:2] < (3, 13)):
        raise RuntimeError(
            "This pipeline must be run with Python 3.11 or 3.12 to match dependencies. "
            f"Current Python: {sys.version}"
        )


def _timestamp_from_epoch(value: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(value))


def _emit_progress(
    progress_callback: Optional[Callable[[Dict[str, object]], None]],
    *,
    step: str,
    percent: int,
    message: str,
    details: Optional[Dict[str, object]] = None,
) -> None:
    if not progress_callback:
        return
    try:
        progress_callback({
            "step": step,
            "percent": int(percent),
            "message": message,
            "details": details or {},
        })
    except Exception:
        return


def run_pipeline_service(
    config: Optional[PipelineRunConfig] = None,
    progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
) -> dict:
    ensure_python_311()
    config = config or PipelineRunConfig()
    os.chdir(REPO_ROOT)

    resolved_staging_dir = resolve_pipeline_staging_dir(config.staging_dir)
    if not resolved_staging_dir.exists():
        raise FileNotFoundError(
            f"{resolved_staging_dir} not found. Place images in {resolved_staging_dir} before starting the pipeline."
        )

    threshold = max(0.0, min(1.0, float(config.confidence_threshold) / 100.0))
    burst_export = "first" if config.remove_burst_duplicates else config.burst_export
    started = time.time()

    print(f"Pipeline start: staging_dir={resolved_staging_dir}")
    print(f"Pipeline start: manifest_path={config.manifest_path}")
    print(f"Pipeline start: metadata_path={config.metadata_path}")
    print(f"Pipeline start: speciesnet_json_path={config.speciesnet_json_path}")
    print(f"Pipeline start: ml_outputs_path={config.ml_outputs_path}")

    print("\n" + "=" * 80)
    print("STEP: Create Manifest")
    print("=" * 80)
    _emit_progress(
        progress_callback,
        step="Create Manifest",
        percent=15,
        message="Building the manifest from staged images",
    )
    manifest_result = build_manifest(
        staging=resolved_staging_dir,
        out=config.manifest_path,
        batch_size=config.manifest_batch_size,
    )
    manifest_path = Path(manifest_result["manifest_path"])

    rows_to_process = int(manifest_result.get("rows_written") or 0)
    print(f"Pipeline manifest to process: {manifest_path} ({rows_to_process} rows)")

    # Apply batch size limit by truncating the manifest to the first N rows
    if config.manifest_batch_size and config.manifest_batch_size > 0 and rows_to_process > config.manifest_batch_size:
        import csv as _csv
        print(
            f"Limiting manifest to first {config.manifest_batch_size} rows "
            f"(batch_size from frontend; full manifest had {rows_to_process})"
        )
        with open(manifest_path, "r", encoding="utf-8", newline="") as _f:
            _reader = _csv.DictReader(_f)
            _fieldnames = _reader.fieldnames or []
            _all_rows = list(_reader)
        _limited_rows = _all_rows[:config.manifest_batch_size]
        with open(manifest_path, "w", encoding="utf-8", newline="") as _f:
            _writer = _csv.DictWriter(_f, fieldnames=_fieldnames)
            _writer.writeheader()
            _writer.writerows(_limited_rows)
        rows_to_process = len(_limited_rows)
        print(f"Manifest truncated to {rows_to_process} rows")

    print("\n" + "=" * 80)
    print("STEP: Extract Metadata (EXIF)")
    print("=" * 80)
    _emit_progress(
        progress_callback,
        step="Extract Metadata (EXIF)",
        percent=28,
        message="Reading EXIF metadata from staged images",
    )
    metadata_exif_result = extract_metadata_from_manifest(
        manifest_path=manifest_path,
        out_path=config.metadata_path,
    )

    print("\n" + "=" * 80)
    print("STEP: Run SpeciesNet")
    print("=" * 80)
    speciesnet_total_images = max(0, int(manifest_result.get("rows_written") or 0))
    _emit_progress(
        progress_callback,
        step="Run SpeciesNet",
        percent=55,
        message="Running SpeciesNet classification on staged images",
        details={
            "processed_images": 0,
            "total_images": speciesnet_total_images,
        },
    )

    def speciesnet_progress_callback(progress: Dict[str, object]) -> None:
        processed_images = max(0, int(progress.get("processed_images") or 0))
        total_images = max(
            processed_images,
            int(progress.get("total_images") or speciesnet_total_images or 0),
        )
        percent = 55
        message = "Running SpeciesNet classification on staged images"
        if total_images > 0:
            percent = min(69, 55 + round((processed_images / total_images) * 14))
            message = (
                "Running SpeciesNet classification on staged images "
                f"({processed_images}/{total_images})"
            )

        _emit_progress(
            progress_callback,
            step="Run SpeciesNet",
            percent=percent,
            message=message,
            details={
                "processed_images": processed_images,
                "total_images": total_images,
            },
        )

    _remove_stale_file(
        config.speciesnet_json_path,
        label="SpeciesNet predictions file",
    )

    # Read the (possibly truncated) manifest to get the exact file list for SpeciesNet
    import csv as _csv_for_sn
    _manifest_filepaths = []
    with open(manifest_path, "r", encoding="utf-8", newline="") as _f:
        for _row in _csv_for_sn.DictReader(_f):
            _local_path = (_row.get("local_path") or "").strip()
            if _local_path:
                _resolved = Path(_local_path)
                if not _resolved.is_absolute():
                    _resolved = REPO_ROOT / _resolved
                _manifest_filepaths.append(str(_resolved))

    print(f"Passing {len(_manifest_filepaths)} explicit filepaths to SpeciesNet")

    speciesnet_result = run_speciesnet_model(
        staging_dir=resolved_staging_dir,
        out_json=config.speciesnet_json_path,
        batch_size=config.speciesnet_batch_size,
        progress_callback=speciesnet_progress_callback,
        filepaths=_manifest_filepaths,
    )

    print("\n" + "=" * 80)
    print("STEP: Postprocess SpeciesNet")
    print("=" * 80)
    _emit_progress(
        progress_callback,
        step="Postprocess SpeciesNet",
        percent=70,
        message="Postprocessing SpeciesNet output against the manifest",
    )
    postprocess_result = postprocess_speciesnet_results(
        in_path=config.speciesnet_json_path,
        manifest_csv=manifest_path,
        metadata_csv=config.metadata_path,
        burst_window_seconds=config.ml_burst_window,
        confidence_threshold=threshold,
    )

    print("\n" + "=" * 80)
    print("STEP: Parse ML Results")
    print("=" * 80)
    _emit_progress(
        progress_callback,
        step="Parse ML Results",
        percent=82,
        message="Converting SpeciesNet output into pipeline CSV results",
    )
    run_speciesnet(
        manifest_csv=manifest_path,
        speciesnet_json=config.speciesnet_json_path,
        out_csv=config.ml_outputs_path,
        threshold=threshold,
        presence_threshold=0.50,
        count_threshold=0.5,
    )
    ml_outputs_result = {
        "ml_outputs_path": str(config.ml_outputs_path),
        "threshold": threshold,
    }

    print("\n" + "=" * 80)
    print("STEP: Extract Metadata (merge ML)")
    print("=" * 80)
    _emit_progress(
        progress_callback,
        step="Extract Metadata (merge ML)",
        percent=90,
        message="Merging ML output back into metadata.csv",
    )
    metadata_merged_result = extract_metadata_from_manifest(
        manifest_path=manifest_path,
        out_path=config.metadata_path,
        ml_path=config.ml_outputs_path,
    )

    print("\n" + "=" * 80)
    print("STEP: Generate Output CSVs")
    print("=" * 80)
    _emit_progress(
        progress_callback,
        step="Generate Output CSVs",
        percent=96,
        message="Generating final export CSVs",
    )
    output_result = generate_output_csvs(
        manifest=manifest_path,
        metadata=config.metadata_path,
        burst_seconds=config.burst_seconds,
        burst_export=burst_export,
        exclude_humans=config.exclude_humans,
    )

    elapsed = time.time() - started
    print(f"\nDONE in {elapsed/60:.1f} minutes")
    _emit_progress(
        progress_callback,
        step="Completed",
        percent=100,
        message="Pipeline completed successfully",
    )

    notes = []
    if not output_result["drive_index_present"]:
        notes.append("drive_index.csv was not present, so output CSVs used fallback camera metadata")

    return {
        "integration_mode": "real_direct_import",
        "started_at": _timestamp_from_epoch(started),
        "finished_at": _timestamp_from_epoch(started + elapsed),
        "elapsed_seconds": round(elapsed, 2),
        "threshold_used": threshold,
        "steps": {
            "manifest": manifest_result,
            "metadata_exif": metadata_exif_result,
            "speciesnet": speciesnet_result,
            "postprocess": postprocess_result,
            "ml_outputs": ml_outputs_result,
            "metadata_merged": metadata_merged_result,
            "output": output_result,
        },
        "notes": notes,
    }
