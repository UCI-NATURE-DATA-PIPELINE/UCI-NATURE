from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Union

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.config import OUT_DIR as CONFIG_STAGING_DIR
from scripts.ml.postprocess_speciesnet import (
    OUT_CSV as POSTPROCESS_RESULTS_CSV,
    REVIEW_CSV as POSTPROCESS_REVIEW_CSV,
    postprocess_speciesnet_results,
)
from scripts.ml.run_inference import (
    OUT_ML,
    SPECIESNET_JSON,
    SUMMARY_JSON as ML_SUMMARY_JSON,
    UNMATCHED_CSV as UNMATCHED_PREDICTIONS_CSV,
    run_speciesnet,
)
from scripts.ml.run_speciesnet import run_speciesnet_model
from scripts.pipeline.extract_metadata import (
    OUT_CSV_DEFAULT as METADATA_CSV_DEFAULT,
    extract_metadata_from_manifest,
    merge_metadata_with_ml_outputs,
)
from scripts.pipeline.make_manifest import (
    CACHE as CACHE_DEFAULT,
    NEW_OUT as NEW_MANIFEST_DEFAULT,
    OUT as MANIFEST_DEFAULT,
    STAGING,
    append_manifest_file_ids_to_cache,
    build_manifest,
)
from scripts.pipeline.make_output import (
    DRIVE_INDEX as DRIVE_INDEX_DEFAULT,
    generate_output_csvs,
)

DEFAULT_STAGING_DIR = Path(CONFIG_STAGING_DIR or STAGING)


def _resolve_repo_path(path: Union[Path, str, None]) -> Optional[Path]:
    if path is None:
        return None
    resolved_path = Path(path)
    return (
        resolved_path
        if resolved_path.is_absolute()
        else (REPO_ROOT / resolved_path).resolve()
    )


def _display_path(path: Optional[Path]) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _remove_stale_file(path: Union[Path, str, None], *, label: str) -> None:
    resolved_path = _resolve_repo_path(path)
    if resolved_path is None or not resolved_path.exists() or not resolved_path.is_file():
        return
    resolved_path.unlink()
    print(f"Removed stale {label}: {_display_path(resolved_path)}")


def resolve_pipeline_staging_dir(path: Optional[Union[Path, str]] = None) -> Path:
    resolved = _resolve_repo_path(path or DEFAULT_STAGING_DIR)
    if resolved is None:
        raise RuntimeError("Pipeline source directory could not be resolved.")
    return resolved


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
    drive_index_path: Optional[Path] = DRIVE_INDEX_DEFAULT
    cache_path: Path = CACHE_DEFAULT
    new_manifest_path: Path = NEW_MANIFEST_DEFAULT
    process_new_only: bool = False
    update_cache_on_success: bool = False


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
        progress_callback(
            {
                "step": step,
                "percent": int(percent),
                "message": message,
                "details": details or {},
            }
        )
    except Exception:
        return


def _build_speciesnet_progress_details(progress: Dict[str, object]) -> Dict[str, object]:
    processed_images = max(0, int(progress.get("processed_images") or 0))
    total_images = max(processed_images, int(progress.get("total_images") or 0))
    percentage = progress.get("percentage")
    if percentage is None:
        percentage = round((processed_images / total_images) * 100) if total_images else 0
    status_text = str(progress.get("status_text") or "").strip()
    return {
        "processed_images": processed_images,
        "total_images": total_images,
        "percentage": int(percentage),
        "status_text": status_text,
    }


def _remove_stale_generated_outputs(config: PipelineRunConfig) -> None:
    for path, label in (
        (config.metadata_path, "metadata CSV"),
        (config.ml_outputs_path, "ML outputs CSV"),
        (config.speciesnet_json_path, "SpeciesNet predictions JSON"),
        (POSTPROCESS_RESULTS_CSV, "SpeciesNet postprocess CSV"),
        (POSTPROCESS_REVIEW_CSV, "SpeciesNet review CSV"),
        (ML_SUMMARY_JSON, "ML summary JSON"),
        (UNMATCHED_PREDICTIONS_CSV, "unmatched predictions CSV"),
    ):
        _remove_stale_file(path, label=label)


def run_pipeline_service(
    config: Optional[PipelineRunConfig] = None,
    progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
) -> dict:
    ensure_python_311()
    config = config or PipelineRunConfig()
    os.chdir(REPO_ROOT)

    resolved_source_dir = resolve_pipeline_staging_dir(config.staging_dir)
    if not resolved_source_dir.exists():
        raise FileNotFoundError(
            f"{resolved_source_dir} not found. Place images in {resolved_source_dir} before starting the pipeline."
        )

    count_threshold = max(0.0, min(1.0, 0.5))
    presence_threshold = min(count_threshold, 0.15)
    burst_export = "first" if config.remove_burst_duplicates else config.burst_export
    started = time.time()

    print(f"Pipeline start: source_dir={resolved_source_dir}")
    print(f"Pipeline start: manifest_path={config.manifest_path}")
    print(f"Pipeline start: new_manifest_path={config.new_manifest_path}")
    print(f"Pipeline start: metadata_path={config.metadata_path}")
    print(f"Pipeline start: speciesnet_json_path={config.speciesnet_json_path}")
    print(f"Pipeline start: ml_outputs_path={config.ml_outputs_path}")
    print(
        "Pipeline start: drive_index_path="
        f"{_display_path(_resolve_repo_path(config.drive_index_path)) or '(none)'}"
    )

    print("\n" + "=" * 80)
    print("STEP: Create Manifest")
    print("=" * 80)
    _emit_progress(
        progress_callback,
        step="Create Manifest",
        percent=15,
        message="Building the manifest from source images",
    )
    manifest_result = build_manifest(
        staging=resolved_source_dir,
        out=config.manifest_path,
        batch_size=config.manifest_batch_size,
        cache_path=config.cache_path,
        new_out=config.new_manifest_path,
        write_new_only=config.process_new_only,
    )
    manifest_path = Path(manifest_result["manifest_path"])
    process_manifest_path = (
        Path(manifest_result.get("new_manifest_path") or config.new_manifest_path)
        if config.process_new_only
        else manifest_path
    )
    raw_rows_to_process = (
        manifest_result.get("new_rows_written")
        if config.process_new_only
        else manifest_result.get("rows_written")
    )
    rows_to_process = int(raw_rows_to_process or 0)
    print(f"Pipeline manifest to process: {process_manifest_path} ({rows_to_process} rows)")

    if rows_to_process <= 0:
        elapsed = time.time() - started
        skip_message = (
            "No new images to process; skipped the ML pipeline."
            if config.process_new_only
            else "No supported images found to process."
        )
        print(skip_message)
        _emit_progress(
            progress_callback,
            step="Completed",
            percent=100,
            message=skip_message,
            details={
                "processed_images": 0,
                "total_images": 0,
                "percentage": 100,
                "status_text": skip_message,
            },
        )
        return {
            "integration_mode": "real_direct_import",
            "started_at": _timestamp_from_epoch(started),
            "finished_at": _timestamp_from_epoch(started + elapsed),
            "elapsed_seconds": round(elapsed, 2),
            "threshold_used": count_threshold,
            "presence_threshold_used": presence_threshold,
            "count_threshold_used": count_threshold,
            "skipped": True,
            "steps": {
                "manifest": manifest_result,
            },
            "notes": [skip_message],
        }

    _remove_stale_generated_outputs(config)

    print("\n" + "=" * 80)
    print("STEP: Extract Metadata (EXIF)")
    print("=" * 80)
    _emit_progress(
        progress_callback,
        step="Extract Metadata (EXIF)",
        percent=28,
        message="Reading EXIF metadata from source images",
    )

    metadata_exif_result = extract_metadata_from_manifest(
    manifest_path=process_manifest_path,
    out_path=config.metadata_path,
    merge_ml=False,
    )
    print(
    f"Metadata extraction complete: "
    f"{metadata_exif_result.get('rows_written', 0)} rows -> {config.metadata_path}"
    )

    print("\n" + "=" * 80)
    print("STEP: Run SpeciesNet")
    print("=" * 80)
    _emit_progress(
        progress_callback,
        step="Run SpeciesNet",
        percent=55,
        message="Running SpeciesNet classification on source images",
        details={
            "processed_images": 0,
            "total_images": rows_to_process,
            "percentage": 0,
            "status_text": "Initializing SpeciesNet",
        },
    )

    def speciesnet_progress_callback(progress: Dict[str, object]) -> None:
        details = _build_speciesnet_progress_details(progress)
        total_images = int(details["total_images"])
        processed_images = int(details["processed_images"])
        percent = 55
        if total_images > 0:
            percent = min(69, 55 + round((processed_images / total_images) * 14))
        message = str(details["status_text"] or "").strip()
        if not message:
            message = (
                "Running SpeciesNet classification on source images "
                f"({processed_images}/{total_images})"
            )

        _emit_progress(
            progress_callback,
            step="Run SpeciesNet",
            percent=percent,
            message=message,
            details=details,
        )

    speciesnet_result = run_speciesnet_model(
        staging_dir=resolved_source_dir,
        out_json=config.speciesnet_json_path,
        batch_size=config.speciesnet_batch_size,
        progress_callback=speciesnet_progress_callback,
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
        manifest_csv=process_manifest_path,
        metadata_csv=config.metadata_path,
        burst_window_seconds=config.ml_burst_window,
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
    ml_outputs_result = run_speciesnet(
    manifest_csv=process_manifest_path,
    speciesnet_json=config.speciesnet_json_path,
    out_csv=config.ml_outputs_path,
    threshold=count_threshold,
    presence_threshold=presence_threshold,
    count_threshold=count_threshold,
    )

    print("\n" + "=" * 80)
    print("STEP: Extract Metadata (merge ML)")
    print("=" * 80)
    _emit_progress(
        progress_callback,
        step="Extract Metadata (merge ML)",
        percent=90,
        message="Merging ML output back into metadata.csv without rereading images",
    )
    metadata_merged_result = merge_metadata_with_ml_outputs(
        metadata_path=config.metadata_path,
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
        manifest=process_manifest_path,
        metadata=config.metadata_path,
        drive_index=config.drive_index_path,
        burst_seconds=config.burst_seconds,
        burst_export=burst_export,
        exclude_humans=config.exclude_humans,
    )

    steps: dict[str, object] = {
        "manifest": manifest_result,
        "metadata_exif": metadata_exif_result,
        "speciesnet": speciesnet_result,
        "postprocess": postprocess_result,
        "ml_outputs": ml_outputs_result,
        "metadata_merged": metadata_merged_result,
        "output": output_result,
    }

    notes: list[str] = []
    if not output_result["drive_index_present"]:
        notes.append(
            "drive_index.csv was not present, so output CSVs used fallback camera metadata"
        )

    if config.update_cache_on_success:
        cache_result = append_manifest_file_ids_to_cache(
            process_manifest_path,
            config.cache_path,
        )
        steps["cache_update"] = cache_result
        print(
            "Updated processed-file cache: "
            f"appended {cache_result['ids_appended']} id(s) -> {config.cache_path}"
        )

    elapsed = time.time() - started
    print(f"\nDONE in {elapsed/60:.1f} minutes")
    _emit_progress(
        progress_callback,
        step="Completed",
        percent=100,
        message="Pipeline completed successfully",
    )

    return {
        "integration_mode": "real_direct_import",
        "started_at": _timestamp_from_epoch(started),
        "finished_at": _timestamp_from_epoch(started + elapsed),
        "elapsed_seconds": round(elapsed, 2),
        "threshold_used": count_threshold,
        "presence_threshold_used": presence_threshold,
        "count_threshold_used": count_threshold,
        "steps": steps,
        "notes": notes,
    }
