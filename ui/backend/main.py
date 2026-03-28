from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime
import importlib.util
from pathlib import Path
import sys
from typing import Dict, List, Optional, Union
import csv
import json
import threading
import traceback

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from scripts.config import PIPELINE_DRIVE_CACHE_POLICY
from scripts.pipeline.validate_output import validate_csv
from ui.backend.auth.routes import get_google_auth_state, router as google_auth_router
from ui.backend.auth.routes_drive import (
    complete_drive_sync_operation,
    fail_drive_sync_operation,
    router as google_drive_router,
    serialize_drive_sync_state,
    start_drive_sync_operation,
    update_drive_sync_progress,
)
from ui.backend.services.drive_staging_service import stage_selected_drive_folder
from ui.backend.session_store import read_session, write_session

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(google_auth_router)
app.include_router(google_drive_router)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "ui" / "backend" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

OUTPUTS_DIR = PROJECT_ROOT / "data" / "outputs"
MANIFEST_CSV = OUTPUTS_DIR / "manifest.csv"
METADATA_CSV = OUTPUTS_DIR / "metadata.csv"
ML_OUTPUTS_CSV = OUTPUTS_DIR / "ml_outputs.csv"
REVIEW_CSV = OUTPUTS_DIR / "speciesnet_review.csv"
BY_LOCATION_DIR = OUTPUTS_DIR / "by_location"
ML_SUMMARY_JSON = OUTPUTS_DIR / "logs" / "ml_summary.json"

PIPELINE_LOCK = threading.Lock()
PIPELINE_STATE = {
    "thread": None,
    "status": "idle",
    "run_id": None,
    "started_at": None,
    "finished_at": None,
    "log_path": None,
    "payload": None,
    "result": None,
    "error": None,
    "integration_mode": None,
    "progress": None,
}


def require_auth(authorization: Optional[str]):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = authorization.replace("Bearer ", "", 1).strip()
    session = read_session()

    if not session.get("token") or session["token"] != token:
        raise HTTPException(status_code=401, detail="Invalid token")

    return session


class LoginRequest(BaseModel):
    email: str
    project: str


class ConnectDriveRequest(BaseModel):
    drive_name: str
    drive_email: str


class RunPipelineRequest(BaseModel):
    source_mode: str = "local"
    confidence_threshold: int
    batch_size: str
    remove_burst_duplicates: bool = True
    exclude_humans: bool = True


def normalize_batch_size(batch_size: str) -> int:
    if batch_size == "all":
        return 0
    try:
        return int(batch_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid batch_size: {batch_size}") from exc


def normalize_source_mode(source_mode: Optional[str]) -> str:
    value = (source_mode or "local").strip().lower()
    if value not in {"local", "drive"}:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source_mode: {source_mode}. Expected 'local' or 'drive'.",
        )
    return value


def get_staging_image_files(staging_dir: Path) -> List[Path]:
    return [
        path
        for path in staging_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]


def read_pipeline_log_summary(log_path: Optional[Union[Path, str]]) -> dict:
    if not log_path:
        return {
            "current_step": None,
            "latest_log_line": None,
        }

    path = Path(log_path)
    if not path.exists():
        return {
            "current_step": None,
            "latest_log_line": None,
        }

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {
            "current_step": None,
            "latest_log_line": None,
        }

    current_step = None
    latest_log_line = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line or set(line) == {"="}:
            continue
        if line.startswith("STEP:"):
            current_step = line.replace("STEP:", "", 1).strip()
        latest_log_line = line

    return {
        "current_step": current_step,
        "latest_log_line": latest_log_line,
    }


def set_pipeline_progress(
    *,
    step: str,
    percent: int,
    message: str,
    details: Optional[dict] = None,
) -> None:
    progress = {
        "step": step,
        "percent": max(0, min(100, int(percent))),
        "message": message,
        "details": details or {},
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    with PIPELINE_LOCK:
        PIPELINE_STATE["progress"] = progress


def serialize_pipeline_state() -> dict:
    thread = PIPELINE_STATE.get("thread")
    status = PIPELINE_STATE.get("status") or "idle"
    run_id = PIPELINE_STATE.get("run_id")
    started_at = PIPELINE_STATE.get("started_at")
    finished_at = PIPELINE_STATE.get("finished_at")
    log_path = PIPELINE_STATE.get("log_path")
    payload = PIPELINE_STATE.get("payload")
    result = PIPELINE_STATE.get("result")
    error = PIPELINE_STATE.get("error")
    integration_mode = PIPELINE_STATE.get("integration_mode")
    progress = deepcopy(PIPELINE_STATE.get("progress"))
    log_summary = read_pipeline_log_summary(log_path)
    current_step = (progress or {}).get("step") or log_summary["current_step"]
    latest_log_line = (progress or {}).get("message") or log_summary["latest_log_line"]

    return {
        "status": status,
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "thread_alive": bool(thread and thread.is_alive()),
        "log_path": str(log_path) if log_path else None,
        "payload": payload,
        "result": result,
        "error": error,
        "integration_mode": integration_mode,
        "progress": progress,
        "current_step": current_step,
        "latest_log_line": latest_log_line,
    }


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    path = Path(path)
    if not path.exists():
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_json_file(path: Path, default):
    path = Path(path)
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def count_csv_rows(path: Path) -> int:
    return len(read_csv_rows(path))


def format_ui_datetime(date_value: str = "", time_value: str = "", fallback: str = "") -> str:
    date_value = (date_value or "").strip()
    time_value = (time_value or "").strip()
    fallback = (fallback or "").strip()

    if date_value:
        try:
            if len(date_value) == 8 and date_value.isdigit():
                dt = datetime.strptime(
                    f"{date_value} {time_value or '00:00:00'}",
                    "%Y%m%d %H:%M:%S",
                )
            else:
                dt = datetime.strptime(
                    f"{date_value} {time_value or '00:00:00'}",
                    "%Y-%m-%d %H:%M:%S",
                )
            return dt.strftime("%b %d, %Y · %H:%M")
        except ValueError:
            pass

    if fallback:
        try:
            return datetime.fromisoformat(fallback).strftime("%b %d, %Y · %H:%M")
        except ValueError:
            return fallback

    return "Unknown"


def format_duration(seconds_value: Optional[Union[float, int]]) -> str:
    if seconds_value is None:
        return "Unknown"
    total = max(0, int(round(float(seconds_value))))
    minutes, seconds = divmod(total, 60)
    return f"{minutes} min {seconds:02d} s"


def get_location_csv_paths() -> List[Path]:
    if not BY_LOCATION_DIR.exists():
        return []
    return sorted(BY_LOCATION_DIR.glob("*.csv"))


def build_camera_map() -> Dict[str, str]:
    camera_map: Dict[str, str] = {}
    for csv_path in get_location_csv_paths():
        for row in read_csv_rows(csv_path):
            image_name = (row.get("Image#") or "").strip()
            camera_name = (row.get("CameraName") or "").strip() or csv_path.stem
            if image_name:
                camera_map[image_name] = camera_name
    return camera_map


def build_metadata_lookup() -> Dict[str, Dict[str, str]]:
    lookup: Dict[str, Dict[str, str]] = {}
    for row in read_csv_rows(METADATA_CSV):
        local_path = (row.get("local_path") or "").strip()
        local_file_name = (row.get("local_file_name") or "").strip()
        if local_path:
            lookup[local_path] = row
        if local_file_name and local_file_name not in lookup:
            lookup[local_file_name] = row
    return lookup


def build_validation_report() -> dict:
    manifest_total = count_csv_rows(MANIFEST_CSV)
    ml_outputs_total = count_csv_rows(ML_OUTPUTS_CSV)
    outside_range = 0
    column_issue_count = 0
    file_reports = []

    for csv_path in get_location_csv_paths():
        rows = read_csv_rows(csv_path)
        result = validate_csv(csv_path)
        issues = result["column_issues"]
        column_issue_count += len(issues)
        outside_for_file = sum(
            1
            for row in rows
            if "outside deployment interval" in ((row.get("Notes") or "").lower())
        )
        outside_range += outside_for_file
        file_reports.append({
            "file": csv_path.name,
            "rows": len(rows),
            "outside_range": outside_for_file,
            "column_issues": issues,
        })

    return {
        "outside_range": outside_range,
        "unprocessed": max(manifest_total - ml_outputs_total, 0),
        "column_issue_count": column_issue_count,
        "files": file_reports,
    }


def build_dashboard_summary_data(project_name: str) -> dict:
    manifest_total = count_csv_rows(MANIFEST_CSV)
    metadata_total = count_csv_rows(METADATA_CSV)
    review_total = count_csv_rows(REVIEW_CSV)
    animals_detected = 0

    for path in get_location_csv_paths():
        for row in read_csv_rows(path):
            has_animal = (row.get("has_animal") or "").strip()
            species = (row.get("Species") or "").strip().lower()
            if has_animal == "1" or species not in ("", "blank", "vehicle", "no cv result"):
                animals_detected += 1

    validation = build_validation_report()
    ml_summary = read_json_file(ML_SUMMARY_JSON, {})

    success_total = int(ml_summary.get("total_predictions_in_json", 0) or 0)
    success_matched = int(ml_summary.get("matched_to_manifest", 0) or 0)
    success_rate = round((success_matched / success_total) * 100) if success_total else 0

    last_run_timestamp = None
    if PIPELINE_STATE.get("finished_at"):
        last_run_timestamp = PIPELINE_STATE["finished_at"]
    elif ML_SUMMARY_JSON.exists():
        last_run_timestamp = datetime.fromtimestamp(ML_SUMMARY_JSON.stat().st_mtime).isoformat()

    if last_run_timestamp:
        try:
            last_run_date = datetime.fromisoformat(last_run_timestamp).strftime("%b %d, %Y")
        except ValueError:
            last_run_date = last_run_timestamp
    else:
        last_run_date = "Unknown"

    last_duration = None
    if isinstance(PIPELINE_STATE.get("result"), dict):
        last_duration = PIPELINE_STATE["result"].get("elapsed_seconds")

    batch_count = len(list((OUTPUTS_DIR / "batches").glob("batch_*.csv"))) if (OUTPUTS_DIR / "batches").exists() else 0

    return {
        "project": project_name,
        "total_images": manifest_total,
        "processed_images": metadata_total,
        "animals_detected": animals_detected,
        "pending_review": review_total,
        "warnings": validation["outside_range"] + validation["unprocessed"] + validation["column_issue_count"],
        "last_run": {
            "batch": f"#{batch_count}" if batch_count else "#0",
            "date": last_run_date,
            "duration": format_duration(last_duration),
            "success_rate": success_rate,
        },
    }


def build_review_items_data() -> List[dict]:
    rows = read_csv_rows(REVIEW_CSV)
    if not rows:
        return []

    camera_map = build_camera_map()
    metadata_lookup = build_metadata_lookup()
    items = []

    for idx, row in enumerate(rows, start=1):
        filepath = (row.get("filepath") or "").strip()
        filename = Path(filepath).name if filepath else f"review-item-{idx}"
        metadata = metadata_lookup.get(filepath) or metadata_lookup.get(filename) or {}
        camera = camera_map.get(filename, "Unknown")
        datetime_label = format_ui_datetime(
            date_value=metadata.get("date", ""),
            time_value=metadata.get("time", ""),
            fallback=metadata.get("modified_time", ""),
        )
        label = (row.get("burst_label") or row.get("label_raw") or "unknown").replace("_", " ").strip()
        confidence = round(float(row.get("score") or 0) * 100)

        items.append({
            "id": idx,
            "filename": filename,
            "species": label.title(),
            "confidence": confidence,
            "camera": camera,
            "datetime": datetime_label,
            "status": "pending",
            "reason": (row.get("reason") or "").strip(),
        })

    return items


def build_export_artifact_summary() -> dict:
    csv_paths = get_location_csv_paths()
    export_files = []
    total_rows = 0

    for path in csv_paths:
        row_count = count_csv_rows(path)
        total_rows += row_count
        export_files.append({
            "name": path.name,
            "rows": row_count,
            "path": str(path.relative_to(PROJECT_ROOT)),
        })

    ready = bool(export_files)
    return {
        "message": "Export artifacts are ready" if ready else "No export artifacts available",
        "status": "ready" if ready else "empty",
        "output_dir": str(BY_LOCATION_DIR.relative_to(PROJECT_ROOT)) if BY_LOCATION_DIR.exists() else str(BY_LOCATION_DIR),
        "file_count": len(export_files),
        "total_rows": total_rows,
        "files": export_files,
        "integration_mode": "artifact_backed",
        "note": "Drive upload is not wired yet; this route returns the generated export artifacts.",
    }


def validate_pipeline_prerequisites(session: dict, source_mode: str) -> dict:
    from ui.backend.services.pipeline_service import resolve_pipeline_staging_dir

    selected_folder = session.get("selected_drive_folder")
    drive_sync = serialize_drive_sync_state(session=session)
    local_staging_dir = resolve_pipeline_staging_dir()
    image_files = get_staging_image_files(local_staging_dir) if local_staging_dir.exists() else []

    if source_mode == "drive":
        if not selected_folder or not selected_folder.get("id"):
            raise HTTPException(
                status_code=400,
                detail="Select a Google Drive folder before running the pipeline in Drive mode.",
            )

        if (drive_sync.get("status") or "idle") == "syncing":
            raise HTTPException(
                status_code=409,
                detail="Drive sync is still in progress. Wait for sync to finish before running the pipeline.",
            )

        google_auth = get_google_auth_state(session=session)
        if not google_auth.get("authenticated") or not google_auth.get("access_token"):
            raise HTTPException(
                status_code=400,
                detail="Google OAuth is not active for this session. Sign in with Google again before running in Drive mode.",
            )

        synced_folder = drive_sync.get("folder") or {}
        cache_ready = bool(
            drive_sync.get("source_ready")
            and synced_folder.get("id") == selected_folder.get("id")
            and image_files
        )

        return {
            "mode": "drive_backend_stage_then_local_pipeline",
            "selected_folder": selected_folder,
            "drive_sync": drive_sync,
            "staging_dir": str(local_staging_dir),
            "image_count": len(image_files),
            "cache_ready": cache_ready,
        }

    if not local_staging_dir.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Local staging is missing at: {local_staging_dir}",
        )

    if not image_files:
        raise HTTPException(
            status_code=400,
            detail=f"Local staging has no supported images at: {local_staging_dir}",
        )

    return {
        "mode": "local_only",
        "selected_folder": None,
        "drive_sync": None,
        "staging_dir": str(local_staging_dir),
        "image_count": len(image_files),
        "cache_ready": False,
    }


def should_reuse_drive_cache(preflight: dict) -> bool:
    policy = (PIPELINE_DRIVE_CACHE_POLICY or "reuse_if_ready").strip().lower()
    if policy == "always_refresh":
        return False
    return bool(preflight.get("cache_ready"))


def validate_pipeline_runtime() -> None:
    python_version = sys.version_info[:2]
    if not ((3, 11) <= python_version < (3, 13)):
        raise HTTPException(
            status_code=500,
            detail=(
                "Pipeline runtime requires Python 3.11 or 3.12 because SpeciesNet is not "
                f"compatible with Python {sys.version_info.major}.{sys.version_info.minor}. "
                f"Current Python: {sys.version}"
            ),
        )

    if importlib.util.find_spec("speciesnet") is None:
        raise HTTPException(
            status_code=500,
            detail=(
                "SpeciesNet is not installed in the active backend environment. "
                "Start the backend with a Python 3.11/3.12 environment that includes the "
                "'speciesnet' package before running the pipeline."
            ),
        )


def execute_pipeline_run(run_id: str, payload: dict, batch_size: int, log_path: Path) -> None:
    result = None
    try:
        with open(log_path, "w", encoding="utf-8", buffering=1) as log_file:
            with redirect_stdout(log_file), redirect_stderr(log_file):
                from ui.backend.services import PipelineRunConfig, run_pipeline_service
                from ui.backend.services.pipeline_service import resolve_pipeline_staging_dir

                set_pipeline_progress(
                    step="Prepare Run",
                    percent=3,
                    message="Preparing the backend pipeline run",
                )

                source_mode = normalize_source_mode(payload.get("source_mode"))
                session = read_session()
                preflight = validate_pipeline_prerequisites(session, source_mode)
                selected_folder = preflight.get("selected_folder")
                drive_sync = preflight.get("drive_sync") or {}
                google_auth = (
                    get_google_auth_state(session=session) if source_mode == "drive" else None
                )

                config = PipelineRunConfig(
                    batch_size=batch_size,
                    confidence_threshold=payload["confidence_threshold"],
                    remove_burst_duplicates=payload["remove_burst_duplicates"],
                    exclude_humans=payload["exclude_humans"],
                )
                configured_staging_dir = config.staging_dir
                config.staging_dir = resolve_pipeline_staging_dir(config.staging_dir)
                resolved_staging_dir = Path(config.staging_dir)

                print(f"Pipeline run {run_id} started at {datetime.now().isoformat(timespec='seconds')}")
                print(f"Payload: {json.dumps(payload, indent=2)}")
                print(f"Source mode: {source_mode}")
                print(f"Configured staging dir: {configured_staging_dir}")
                print(f"Resolved staging dir: {resolved_staging_dir}")

                if source_mode == "drive" and selected_folder and selected_folder.get("id"):
                    reuse_cache = should_reuse_drive_cache(preflight)
                    if reuse_cache:
                        set_pipeline_progress(
                            step="Reuse Backend Cache",
                            percent=8,
                            message=(
                                f"Reusing the staged backend cache for "
                                f"{selected_folder.get('name') or selected_folder['id']}"
                            ),
                        )
                        print(
                            "Drive source cache: "
                            f"reusing staged backend files for {selected_folder.get('name') or selected_folder['id']}"
                        )
                    else:
                        set_pipeline_progress(
                            step="Sync Google Drive Folder",
                            percent=5,
                            message=(
                                f"Staging {selected_folder.get('name') or selected_folder['id']} "
                                "from Google Drive onto the backend server"
                            ),
                        )
                        start_drive_sync_operation(
                            session,
                            folder=selected_folder,
                            staging_dir=str(resolved_staging_dir),
                            message=(
                                f"Staging {selected_folder.get('name') or selected_folder['id']} "
                                "into backend cache"
                            ),
                        )

                        def drive_progress_callback(progress: dict) -> None:
                            discovered_count = int(progress.get("discovered_count") or 0)
                            downloaded_count = int(progress.get("downloaded_count") or 0)
                            current_file = progress.get("current_file")
                            status_message = (
                                f"Downloaded {downloaded_count} of {discovered_count} "
                                f"image(s) from Google Drive"
                            )
                            if current_file:
                                status_message = f"{status_message}: {current_file}"

                            update_drive_sync_progress(
                                folder=selected_folder,
                                discovered_count=discovered_count,
                                downloaded_count=downloaded_count,
                                current_file=current_file,
                                staging_dir=progress.get("staging_dir"),
                                message=status_message,
                            )
                            sync_percent = 5
                            if discovered_count > 0:
                                sync_percent = min(
                                    14,
                                    5 + round((downloaded_count / discovered_count) * 9),
                                )
                            set_pipeline_progress(
                                step="Sync Google Drive Folder",
                                percent=sync_percent,
                                message=status_message,
                                details={
                                    "discovered_count": discovered_count,
                                    "downloaded_count": downloaded_count,
                                    "current_file": current_file,
                                },
                            )

                        try:
                            sync_result = stage_selected_drive_folder(
                                access_token=(google_auth or {}).get("access_token"),
                                refresh_token=(google_auth or {}).get("refresh_token"),
                                folder_id=selected_folder["id"],
                                folder_name=selected_folder.get("name") or selected_folder["id"],
                                staging_dir=resolved_staging_dir,
                                progress_callback=drive_progress_callback,
                            )
                            complete_drive_sync_operation(
                                session,
                                folder=selected_folder,
                                sync_result=sync_result,
                                message=(
                                    f"Staged {int(sync_result.get('downloaded_count') or 0)} "
                                    f"image(s) from {selected_folder.get('name') or selected_folder['id']}"
                                ),
                            )
                            drive_sync = serialize_drive_sync_state(session=read_session())
                            preflight["image_count"] = int(
                                sync_result.get("downloaded_count")
                                or sync_result.get("discovered_count")
                                or 0
                            )
                        except FileNotFoundError as exc:
                            fail_drive_sync_operation(
                                session,
                                folder=selected_folder,
                                error=str(exc),
                                message="Drive staging failed during pipeline run",
                            )
                            raise
                        except Exception as exc:
                            fail_drive_sync_operation(
                                session,
                                folder=selected_folder,
                                error=f"Failed to stage the selected Drive folder: {exc}",
                                message="Drive staging failed during pipeline run",
                            )
                            raise

                    print(
                        "Drive source summary: "
                        f"mode=drive_backend_stage_then_local_pipeline, "
                        f"folder_id={selected_folder['id']}, "
                        f"folder_name={selected_folder.get('name') or selected_folder['id']}, "
                        f"cache_reused={should_reuse_drive_cache(preflight)}, "
                        f"discovered_count={drive_sync.get('discovered_count', 0)}, "
                        f"downloaded_count={drive_sync.get('downloaded_count', 0)}, "
                        f"staging_dir={drive_sync.get('staging_dir') or resolved_staging_dir}, "
                        f"drive_index_path={drive_sync.get('drive_index_path')}"
                    )
                else:
                    set_pipeline_progress(
                        step="Prepare Local Source",
                        percent=5,
                        message="Using the current local staging directory",
                    )
                    print("Drive-backed pre-run staging skipped: using local staging contents")
                    print(f"Final staging dir path: {resolved_staging_dir}")
                    print(
                        "Local source summary: "
                        f"mode=local_only, image_count={preflight.get('image_count', 0)}, "
                        f"staging_dir={resolved_staging_dir}"
                    )

                print("Pipeline start: invoking existing run_pipeline_service")
                print(f"Pipeline start: staging_dir={resolved_staging_dir}")
                print(f"Pipeline start: manifest_path={config.manifest_path}")
                print(f"Pipeline start: metadata_path={config.metadata_path}")
                print(f"Pipeline start: speciesnet_json_path={config.speciesnet_json_path}")
                print(f"Pipeline start: ml_outputs_path={config.ml_outputs_path}")

                result = run_pipeline_service(
                    config,
                    progress_callback=lambda progress: set_pipeline_progress(
                        step=str(progress.get("step") or "Pipeline Running"),
                        percent=int(progress.get("percent") or 0),
                        message=str(progress.get("message") or "Pipeline running"),
                        details=(
                            progress.get("details")
                            if isinstance(progress.get("details"), dict)
                            else {}
                        ),
                    ),
                )

                if isinstance(result, dict):
                    result["source"] = {
                        "mode": source_mode,
                        "staging_dir": str(resolved_staging_dir),
                        "image_count": preflight.get("image_count"),
                    }
                    if source_mode == "drive" and selected_folder:
                        result["source"].update({
                            "folder_id": selected_folder.get("id"),
                            "folder_name": selected_folder.get("name"),
                            "cache_reused": should_reuse_drive_cache(preflight),
                            "discovered_count": drive_sync.get("discovered_count"),
                            "downloaded_count": drive_sync.get("downloaded_count"),
                            "drive_index_path": drive_sync.get("drive_index_path"),
                        })

                print(f"Pipeline run {run_id} completed successfully")

        with PIPELINE_LOCK:
            PIPELINE_STATE["status"] = "completed"
            PIPELINE_STATE["finished_at"] = datetime.now().isoformat(timespec="seconds")
            PIPELINE_STATE["result"] = result
            PIPELINE_STATE["error"] = None
            PIPELINE_STATE["progress"] = {
                "step": "Completed",
                "percent": 100,
                "message": "Pipeline completed successfully",
                "details": {},
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }

    except Exception as exc:
        with open(log_path, "a", encoding="utf-8", buffering=1) as log_file:
            with redirect_stdout(log_file), redirect_stderr(log_file):
                print(f"Pipeline run {run_id} failed")
                traceback.print_exc()

        with PIPELINE_LOCK:
            PIPELINE_STATE["status"] = "failed"
            PIPELINE_STATE["finished_at"] = datetime.now().isoformat(timespec="seconds")
            PIPELINE_STATE["result"] = None
            PIPELINE_STATE["error"] = str(exc)
            PIPELINE_STATE["progress"] = {
                "step": "Failed",
                "percent": 100,
                "message": str(exc),
                "details": {},
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }


def start_pipeline_thread(data: RunPipelineRequest) -> dict:
    with PIPELINE_LOCK:
        current = serialize_pipeline_state()
        if current["status"] == "running":
            raise HTTPException(
                status_code=409,
                detail="A pipeline run is already in progress. Check /api/pipeline/status for details.",
            )

        session = read_session()
        validate_pipeline_runtime()
        source_mode = normalize_source_mode(data.source_mode)
        preflight = validate_pipeline_prerequisites(session, source_mode)

        batch_size = normalize_batch_size(data.batch_size)
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = LOG_DIR / f"pipeline_{run_id}.log"
        payload = data.dict()
        payload["source_mode"] = source_mode

        thread = threading.Thread(
            target=execute_pipeline_run,
            args=(run_id, payload, batch_size, log_path),
            daemon=True,
            name=f"pipeline-{run_id}",
        )

        PIPELINE_STATE["thread"] = thread
        PIPELINE_STATE["status"] = "running"
        PIPELINE_STATE["run_id"] = run_id
        PIPELINE_STATE["started_at"] = datetime.now().isoformat(timespec="seconds")
        PIPELINE_STATE["finished_at"] = None
        PIPELINE_STATE["log_path"] = log_path
        PIPELINE_STATE["payload"] = payload
        PIPELINE_STATE["result"] = None
        PIPELINE_STATE["error"] = None
        PIPELINE_STATE["integration_mode"] = preflight["mode"]
        PIPELINE_STATE["progress"] = {
            "step": "Queued",
            "percent": 1,
            "message": "Pipeline run queued on the backend",
            "details": {
                "source_mode": source_mode,
                "cache_ready": bool(preflight.get("cache_ready")),
            },
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

        thread.start()
        return serialize_pipeline_state()


@app.get("/")
def root():
    return {"message": "Backend running"}


@app.post("/api/auth/login")
def login(data: LoginRequest):
    token = "demo-token"

    session = read_session()
    session["token"] = token
    session["user"] = {
        "email": data.email,
        "project": data.project,
    }
    session["drive_connected"] = session.get("drive_connected", False)
    session["drive_name"] = session.get("drive_name")
    session["drive_email"] = session.get("drive_email")
    write_session(session)

    return {
        "access_token": token,
        "user": session["user"],
    }


@app.get("/api/auth/me")
def auth_me(authorization: Optional[str] = Header(default=None)):
    session = require_auth(authorization)
    return session["user"]


@app.post("/api/drive/connect")
def connect_drive(
    data: ConnectDriveRequest,
    authorization: Optional[str] = Header(default=None),
):
    session = require_auth(authorization)

    google_auth = get_google_auth_state(session=session)
    if not google_auth.get("authenticated"):
        raise HTTPException(
            status_code=400,
            detail="Google OAuth is not active. Sign in with Google before connecting Drive.",
        )

    session["drive_connected"] = True
    session["drive_name"] = data.drive_name
    session["drive_email"] = data.drive_email
    write_session(session)

    return {
        "connected": True,
        "drive_name": data.drive_name,
        "drive_email": data.drive_email,
    }


@app.get("/api/drive/status")
def drive_status(authorization: Optional[str] = Header(default=None)):
    session = require_auth(authorization)
    google_auth = get_google_auth_state(session=session)

    return {
        "connected": session.get("drive_connected", False),
        "drive_name": session.get("drive_name"),
        "drive_email": session.get("drive_email"),
        "selected_folder": session.get("selected_drive_folder"),
        "sync": serialize_drive_sync_state(session=session),
        "google_authenticated": bool(google_auth.get("authenticated")),
        "google_user": google_auth.get("user"),
    }


@app.get("/api/dashboard/summary")
def dashboard_summary(authorization: Optional[str] = Header(default=None)):
    session = require_auth(authorization)
    return build_dashboard_summary_data(session["user"]["project"])


@app.post("/api/pipeline/run")
def run_pipeline(
    data: RunPipelineRequest,
    authorization: Optional[str] = Header(default=None),
):
    require_auth(authorization)
    session = read_session()
    state = start_pipeline_thread(data)
    source_mode = normalize_source_mode(data.source_mode)

    return {
        "message": "Pipeline started on the backend using the selected source mode",
        "status": state["status"],
        "run_id": state["run_id"],
        "started_at": state["started_at"],
        "log_path": state["log_path"],
        "received": data.dict(),
        "integration_mode": state["integration_mode"],
        "source_mode": source_mode,
        "selected_drive_folder": session.get("selected_drive_folder"),
        "note": (
            "Runs now use an explicit source_mode. Drive mode stages the selected folder on "
            "the backend server when needed and can reuse a warm backend cache when one is "
            "already ready. Local mode still uses the existing local staging flow."
        ),
    }


@app.get("/api/pipeline/status")
def pipeline_status(authorization: Optional[str] = Header(default=None)):
    require_auth(authorization)
    return serialize_pipeline_state()


@app.get("/api/review/items")
def review_items(authorization: Optional[str] = Header(default=None)):
    require_auth(authorization)
    return build_review_items_data()


@app.get("/api/validate/issues")
def validate_issues(authorization: Optional[str] = Header(default=None)):
    require_auth(authorization)
    return build_validation_report()


@app.post("/api/export/start")
def export_start(authorization: Optional[str] = Header(default=None)):
    require_auth(authorization)
    return build_export_artifact_summary()
